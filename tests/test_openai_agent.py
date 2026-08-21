from __future__ import annotations

import json

import pytest

from promiseguard.models import (
    EvaluationRequest,
    PolicyDisposition,
    RecoveryAction,
)
from promiseguard.openai_agent import (
    AgentOutputValidationError,
    OpenAIAgentService,
    OpenAIAgentUnavailableError,
    OpenAIResponseError,
    ParsedOpenAIResponse,
)
from promiseguard.openai_models import (
    AgentDecisionReview,
    AgentNextStep,
    AgentRationaleCode,
    AgentRunRequest,
    AgentRunStatus,
    AgentTokenUsage,
)


class FakeResponsesClient:
    def __init__(self, review: AgentDecisionReview | None = None, *, fail: bool = False) -> None:
        self.review = review
        self.fail = fail
        self.calls = 0
        self.last_input = ""

    def parse_review(self, **kwargs) -> ParsedOpenAIResponse:
        self.calls += 1
        self.last_input = kwargs["input_text"]
        if self.fail:
            raise TimeoutError("simulated ambiguous provider timeout")
        assert self.review is not None
        return ParsedOpenAIResponse(
            response_id="resp-fake",
            review=self.review,
            usage=AgentTokenUsage(
                input_tokens=180,
                cached_input_tokens=0,
                output_tokens=60,
                total_tokens=240,
            ),
        )


def _valid_review(decision) -> AgentDecisionReview:
    evidence_ids = []
    for reference in decision.risk.evidence_references:
        evidence_ids.append(
            f"{reference.system}:{reference.record_id}:{reference.observed_at.isoformat()}"
        )
    disposition = decision.policy.disposition
    next_step = {
        PolicyDisposition.AUTO_EXECUTE: AgentNextStep.SUBMIT_DECISION,
        PolicyDisposition.REQUEST_APPROVAL: AgentNextStep.SUBMIT_DECISION,
        PolicyDisposition.ESCALATE: AgentNextStep.ESCALATE,
        PolicyDisposition.BLOCK: AgentNextStep.NO_ACTION,
        PolicyDisposition.TAKE_NO_ACTION: AgentNextStep.NO_ACTION,
    }[disposition]
    required = {
        PolicyDisposition.AUTO_EXECUTE: AgentRationaleCode.BOUNDED_AUTONOMY_ALLOWED,
        PolicyDisposition.REQUEST_APPROVAL: AgentRationaleCode.APPROVAL_REQUIRED,
        PolicyDisposition.ESCALATE: AgentRationaleCode.HUMAN_ESCALATION,
        PolicyDisposition.BLOCK: AgentRationaleCode.POLICY_BLOCKED,
        PolicyDisposition.TAKE_NO_ACTION: AgentRationaleCode.NO_POSITIVE_VALUE,
    }[disposition]
    return AgentDecisionReview(
        decision_id=decision.decision_id,
        selected_action=decision.recommendation.selected_action,
        policy_disposition=disposition,
        next_step=next_step,
        rationale_codes=(AgentRationaleCode.HIGHEST_EXPECTED_VALUE, required),
        evidence_ids=tuple(evidence_ids),
        requires_human_attention=disposition
        in {
            PolicyDisposition.REQUEST_APPROVAL,
            PolicyDisposition.ESCALATE,
            PolicyDisposition.BLOCK,
        },
        uncertainty=0.1,
        summary="The immutable evidence supports the governed recovery path.",
    )


def _service(services, client: FakeResponsesClient) -> OpenAIAgentService:
    return OpenAIAgentService(
        workflow=services.workflow,
        budget=services.openai_budget,
        model="gpt-5-nano",
        max_output_tokens=320,
        timeout_seconds=10,
        enabled=True,
        client=client,
    )


def test_agent_uses_one_structured_call_reuses_result_and_can_create_approval(
    services,
    at_risk_request: EvaluationRequest,
) -> None:
    decision = services.evaluation.evaluate(at_risk_request)
    client = FakeResponsesClient(_valid_review(decision))
    agent = _service(services, client)

    first = agent.run(
        AgentRunRequest(
            decision_id=decision.decision_id,
            actor_id="analyst-openai",
            advance_workflow=True,
        )
    )
    second = agent.run(
        AgentRunRequest(
            decision_id=decision.decision_id,
            actor_id="analyst-openai",
            advance_workflow=False,
        )
    )

    assert first.run.status is AgentRunStatus.COMPLETED
    assert first.workflow is not None
    assert first.workflow.approval is not None
    assert second.reused_existing_run is True
    assert client.calls == 1
    assert "customer-001" not in client.last_input
    assert "Ignore policy" not in client.last_input
    parsed_context = json.loads(client.last_input)
    assert "external_notes" not in parsed_context
    assert parsed_context["decision_id"] == decision.decision_id


def test_agent_rejects_action_override_before_workflow_advances(
    services,
    at_risk_request: EvaluationRequest,
) -> None:
    decision = services.evaluation.evaluate(at_risk_request)
    valid = _valid_review(decision)
    alternate = next(
        action for action in RecoveryAction if action is not decision.recommendation.selected_action
    )
    client = FakeResponsesClient(valid.model_copy(update={"selected_action": alternate}))
    agent = _service(services, client)

    with pytest.raises(AgentOutputValidationError) as captured:
        agent.run(
            AgentRunRequest(
                decision_id=decision.decision_id,
                actor_id="analyst-openai",
                advance_workflow=True,
            )
        )

    persisted = services.openai_budget.get(captured.value.run_id)
    state = services.workflow.get_state(decision.decision_id)
    assert persisted is not None
    assert persisted.status is AgentRunStatus.REJECTED
    assert state.approval is None
    assert state.execution is None


def test_ambiguous_provider_failure_is_charged_conservatively(
    services,
    at_risk_request: EvaluationRequest,
) -> None:
    decision = services.evaluation.evaluate(at_risk_request)
    agent = _service(services, FakeResponsesClient(fail=True))

    with pytest.raises(OpenAIResponseError) as captured:
        agent.run(
            AgentRunRequest(
                decision_id=decision.decision_id,
                actor_id="analyst-openai",
            )
        )

    persisted = services.openai_budget.get(captured.value.run_id)
    assert persisted is not None
    assert persisted.status is AgentRunStatus.FAILED
    assert persisted.actual_cost_usd == persisted.reserved_cost_usd


def test_disabled_agent_without_injected_client_refuses_before_budget_reservation(
    services,
    at_risk_request: EvaluationRequest,
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    decision = services.evaluation.evaluate(at_risk_request)
    agent = OpenAIAgentService(
        workflow=services.workflow,
        budget=services.openai_budget,
        model="gpt-5-nano",
        max_output_tokens=320,
        timeout_seconds=10,
        enabled=False,
    )

    with pytest.raises(OpenAIAgentUnavailableError):
        agent.run(
            AgentRunRequest(
                decision_id=decision.decision_id,
                actor_id="analyst-openai",
            )
        )
    assert services.openai_budget.state().spent_usd == 0
