from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.main import app
from promiseguard.models import EvaluationRequest, RecoveryAction

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_shadow_evaluation_endpoint(at_risk_request: EvaluationRequest) -> None:
    response = client.post(
        "/v1/shadow/evaluate",
        json=at_risk_request.model_dump(mode="json"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["recommendation"]["selected_action"] == RecoveryAction.REROUTE.value
    assert body["policy"]["execution_allowed"] is False
