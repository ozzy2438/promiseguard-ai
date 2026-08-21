from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from apps.api.main import create_app
from promiseguard.config import Settings
from promiseguard.models import (
    ApprovalStatus,
    EvaluationRequest,
    OperatingMode,
    RecoveryAction,
    UserRole,
)


def _client() -> TestClient:
    return TestClient(
        create_app(
            Settings(
                database_url="sqlite+pysqlite:///:memory:",
                environment="test",
                auto_create_schema=True,
            )
        )
    )


def test_health_and_readiness_endpoints() -> None:
    with _client() as client:
        health = client.get("/healthz")
        ready = client.get("/readyz")

        assert health.status_code == 200
        assert health.json() == {"status": "ok"}
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"


def test_persistent_approval_execution_and_verification_api(
    at_risk_request: EvaluationRequest,
    evaluation_time,
) -> None:
    with _client() as client:
        approval_request = at_risk_request.model_copy(update={"mode": OperatingMode.APPROVAL})

        evaluation = client.post(
            "/v1/evaluate",
            json=approval_request.model_dump(mode="json"),
        )
        assert evaluation.status_code == 200
        decision = evaluation.json()
        assert decision["recommendation"]["selected_action"] == RecoveryAction.REROUTE.value

        listed = client.get("/v1/decisions?limit=10")
        assert listed.status_code == 200
        assert listed.json()[0]["decision_id"] == decision["decision_id"]

        submitted = client.post(
            f"/v1/decisions/{decision['decision_id']}/submit",
            json={"actor_id": "analyst-1"},
        )
        assert submitted.status_code == 200
        approval = submitted.json()["approval"]
        assert approval["status"] == ApprovalStatus.PENDING.value

        approved = client.post(
            f"/v1/approvals/{approval['approval_id']}/approve",
            json={
                "actor_id": "manager-1",
                "actor_role": UserRole.OPERATIONS_MANAGER.value,
                "reason": "Validated recovery action",
            },
        )
        assert approved.status_code == 200
        assert approved.json()["execution"]["status"] == "SUCCEEDED"

        observed_at = evaluation_time + timedelta(days=1)
        verified = client.post(
            f"/v1/decisions/{decision['decision_id']}/verify",
            json={
                "order_id": at_risk_request.order.order_id,
                "delivered_on_time": True,
                "observed_at": observed_at.isoformat(),
                "source_reference": {
                    "system": "carrier",
                    "record_id": "delivery-confirmation-1",
                    "observed_at": observed_at.isoformat(),
                },
            },
        )
        assert verified.status_code == 200
        assert verified.json()["outcome"]["status"] == "VERIFIED"

        fetched = client.get(f"/v1/decisions/{decision['decision_id']}")
        assert fetched.status_code == 200
        assert fetched.json()["outcome"]["status"] == "VERIFIED"


def test_metrics_endpoint_contains_decision_counter(
    at_risk_request: EvaluationRequest,
) -> None:
    with _client() as client:
        response = client.post(
            "/v1/shadow/evaluate",
            json=at_risk_request.model_dump(mode="json"),
        )
        assert response.status_code == 200

        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "promiseguard_decisions_total" in metrics.text


def test_missing_decision_returns_structured_404() -> None:
    with _client() as client:
        response = client.get("/v1/decisions/does-not-exist")

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "NOT_FOUND"


def test_decision_list_rejects_unbounded_limit() -> None:
    with _client() as client:
        response = client.get("/v1/decisions?limit=501")
        assert response.status_code == 422


def test_runtime_control_endpoints_enforce_manager_authority() -> None:
    with _client() as client:
        initial = client.get("/v1/controls/kill-switch")
        assert initial.status_code == 200
        assert initial.json()["active"] is False

        denied = client.post(
            "/v1/controls/kill-switch",
            json={
                "active": True,
                "actor_id": "auditor-1",
                "actor_role": UserRole.AUDITOR.value,
                "reason": "Attempted unauthorised activation",
            },
        )
        assert denied.status_code == 409
        assert denied.json()["detail"]["code"] == "AUTONOMY_CONTROL_ERROR"

        enabled = client.post(
            "/v1/controls/kill-switch",
            json={
                "active": True,
                "actor_id": "manager-1",
                "actor_role": UserRole.OPERATIONS_MANAGER.value,
                "reason": "Containment during operational incident",
            },
        )
        assert enabled.status_code == 200
        assert enabled.json()["active"] is True
        assert enabled.json()["version"] == 2

        ready = client.get("/readyz")
        assert ready.status_code == 200
        assert ready.json()["kill_switch"] == "true"


def test_autonomy_profile_api_exposes_evidence_gate() -> None:
    with _client() as client:
        listed = client.get("/v1/autonomy")
        assert listed.status_code == 200
        assert {profile["action"] for profile in listed.json()} == {
            "REROUTE",
            "CARRIER_UPGRADE",
            "SPLIT_SHIPMENT",
        }
        assert all(profile["level"] == "APPROVAL_REQUIRED" for profile in listed.json())

        denied = client.post(
            "/v1/autonomy/REROUTE",
            json={
                "level": "BOUNDED_AUTONOMY",
                "actor_id": "manager-1",
                "actor_role": UserRole.OPERATIONS_MANAGER.value,
                "reason": "Premature promotion",
            },
        )
        assert denied.status_code == 409
        assert "consecutive verified evidence" in denied.json()["detail"]["message"]
