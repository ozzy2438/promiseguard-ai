from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from promiseguard.config import Settings
from promiseguard.identity import IdentityError, bind_claimed_role
from promiseguard.models import (
    ApprovalDecisionInput,
    EvaluationRequest,
    OperatingMode,
    OperatorFeedbackInput,
    UserRole,
)
from promiseguard.services import ServiceContainer


def test_registered_identity_cannot_claim_a_different_role() -> None:
    with pytest.raises(IdentityError, match="registered as"):
        bind_claimed_role("operations-manager-ui", UserRole.AUDITOR)


def test_strict_local_identity_rejects_unknown_actors() -> None:
    with pytest.raises(IdentityError, match="not in the local identity directory"):
        bind_claimed_role("manager-1", UserRole.OPERATIONS_MANAGER, strict=True)


def test_requester_cannot_approve_their_own_request(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
    evaluation_time,
) -> None:
    trace = services.evaluation.evaluate(
        at_risk_request.model_copy(update={"mode": OperatingMode.APPROVAL})
    )
    pending = services.workflow.submit(
        trace.decision_id,
        actor_id="analyst-1",
        now=evaluation_time,
    ).approval
    assert pending is not None
    with pytest.raises(IdentityError, match="requester cannot"):
        services.workflow.approve_and_execute(
            pending.approval_id,
            ApprovalDecisionInput(
                actor_id="analyst-1",
                actor_role=UserRole.OPERATIONS_ANALYST,
                reason="Self-approval attempt",
            ),
            now=evaluation_time + timedelta(minutes=1),
        )


def test_tenant_list_is_isolated(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
) -> None:
    default_trace = services.evaluation.evaluate(at_risk_request)
    other = at_risk_request.model_copy(
        update={
            "event": at_risk_request.event.model_copy(
                update={
                    "event_id": "evt-tenant-b",
                    "deduplication_key": "oms:evt-tenant-b:v1",
                }
            ),
            "order": at_risk_request.order.model_copy(
                update={"order_id": "order-tenant-b", "tenant_id": "retailer-b"}
            ),
        }
    )
    other_trace = services.evaluation.evaluate(other)
    default_listed = services.ledger.list_recent(limit=10, tenant_id="local-default")
    other_listed = services.ledger.list_recent(limit=10, tenant_id="retailer-b")
    assert default_trace.decision_id in {item.decision_id for item in default_listed}
    assert other_trace.decision_id not in {item.decision_id for item in default_listed}
    assert other_listed == (other_trace,)


def test_api_rejects_role_spoofing_for_registered_identities(
    at_risk_request: EvaluationRequest,
) -> None:
    client = TestClient(
        create_app(
            Settings(
                database_url="sqlite+pysqlite:///:memory:",
                environment="test",
                auto_create_schema=True,
            )
        )
    )
    with client:
        evaluated = client.post(
            "/v1/evaluate",
            json=at_risk_request.model_copy(update={"mode": OperatingMode.APPROVAL}).model_dump(
                mode="json"
            ),
        )
        decision_id = evaluated.json()["decision_id"]
        submitted = client.post(
            f"/v1/decisions/{decision_id}/submit",
            json={"actor_id": "operations-analyst-ui"},
        )
        approval_id = submitted.json()["approval"]["approval_id"]
        spoofed = client.post(
            f"/v1/approvals/{approval_id}/approve",
            json={
                "actor_id": "operations-analyst-ui",
                "actor_role": UserRole.OPERATIONS_MANAGER.value,
                "reason": "Attempted privilege escalation",
            },
        )
        assert spoofed.status_code == 403
        assert spoofed.json()["detail"]["code"] == "IDENTITY_ERROR"


def test_operator_feedback_is_persisted(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
) -> None:
    trace = services.evaluation.evaluate(at_risk_request)
    recorded = services.feedback.record(
        trace.decision_id,
        OperatorFeedbackInput(
            actor_id="operations-analyst-ui",
            actor_role=UserRole.OPERATIONS_ANALYST,
            useful=True,
            expected_outcome_matched=None,
            comment="Shadow recommendation matches the evidence pack.",
        ),
    )
    listed = services.feedback.list_for_decision(trace.decision_id)
    assert listed == (recorded,)
    assert recorded.useful is True
