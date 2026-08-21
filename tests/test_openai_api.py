from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from apps.api.main import create_app
from promiseguard.config import Settings
from promiseguard.models import EvaluationRequest, PolicyDisposition
from promiseguard.openai_agent import ParsedOpenAIResponse
from promiseguard.openai_models import (
    AgentDecisionReview,
    AgentNextStep,
    AgentRationaleCode,
    AgentTokenUsage,
)


class ContextAwareFakeClient:
    def parse_review(self, **kwargs) -> ParsedOpenAIResponse:
        import json

        context = json.loads(kwargs["input_text"])
        disposition = PolicyDisposition(context["policy"]["disposition"])
        next_step = (
            AgentNextStep.SUBMIT_DECISION
            if disposition in {PolicyDisposition.AUTO_EXECUTE, PolicyDisposition.REQUEST_APPROVAL}
            else AgentNextStep.NO_ACTION
        )
        required = {
            PolicyDisposition.AUTO_EXECUTE: AgentRationaleCode.BOUNDED_AUTONOMY_ALLOWED,
            PolicyDisposition.REQUEST_APPROVAL: AgentRationaleCode.APPROVAL_REQUIRED,
            PolicyDisposition.ESCALATE: AgentRationaleCode.HUMAN_ESCALATION,
            PolicyDisposition.BLOCK: AgentRationaleCode.POLICY_BLOCKED,
            PolicyDisposition.TAKE_NO_ACTION: AgentRationaleCode.NO_POSITIVE_VALUE,
        }[disposition]
        review = AgentDecisionReview(
            decision_id=context["decision_id"],
            selected_action=context["recommendation"]["selected_action"],
            policy_disposition=disposition,
            next_step=next_step,
            rationale_codes=(AgentRationaleCode.HIGHEST_EXPECTED_VALUE, required),
            evidence_ids=(context["allowed_evidence_ids"][0],),
            requires_human_attention=disposition
            in {
                PolicyDisposition.REQUEST_APPROVAL,
                PolicyDisposition.ESCALATE,
                PolicyDisposition.BLOCK,
            },
            uncertainty=0.1,
            summary="The governed recovery path matches the immutable evidence.",
        )
        return ParsedOpenAIResponse(
            response_id="resp-api-fake",
            review=review,
            usage=AgentTokenUsage(
                input_tokens=120,
                cached_input_tokens=0,
                output_tokens=40,
                total_tokens=160,
            ),
        )


def _client() -> TestClient:
    return TestClient(
        create_app(
            Settings(
                database_url="sqlite+pysqlite:///:memory:",
                environment="test-openai-api",
                auto_create_schema=True,
                openai_enabled=True,
            ),
            openai_client=ContextAwareFakeClient(),
        )
    )


def test_openai_budget_and_structured_run_endpoints(
    at_risk_request: EvaluationRequest,
) -> None:
    with _client() as client:
        evaluation = client.post(
            "/v1/evaluate",
            json=at_risk_request.model_dump(mode="json"),
        )
        assert evaluation.status_code == 200
        decision_id = evaluation.json()["decision_id"]

        budget_before = client.get("/v1/agent/budget")
        assert budget_before.status_code == 200
        assert Decimal(str(budget_before.json()["limit_usd"])) == Decimal("3.00")

        run = client.post(
            "/v1/agent/run",
            json={
                "decision_id": decision_id,
                "actor_id": "api-test",
                "advance_workflow": False,
            },
        )
        assert run.status_code == 200
        payload = run.json()
        assert payload["run"]["status"] == "COMPLETED"
        assert payload["run"]["model"] == "gpt-5-nano"
        assert payload["workflow"]["decision"]["decision_id"] == decision_id

        fetched = client.get(f"/v1/agent/runs/{payload['run']['run_id']}")
        assert fetched.status_code == 200
        assert fetched.json()["response_id"] == "resp-api-fake"

        metrics = client.get("/metrics")
        assert "promiseguard_openai_runs_total" in metrics.text
        assert "promiseguard_openai_cost_usd_total" in metrics.text


def test_missing_run_returns_structured_404() -> None:
    with _client() as client:
        response = client.get("/v1/agent/runs/missing")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "OPENAI_RUN_NOT_FOUND"
