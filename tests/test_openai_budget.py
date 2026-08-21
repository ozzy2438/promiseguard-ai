from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from promiseguard.models import EvaluationRequest
from promiseguard.openai_budget import (
    OpenAIBudgetExceededError,
    OpenAIBudgetManager,
    OpenAIPerRunLimitError,
)
from promiseguard.openai_models import (
    AgentDecisionReview,
    AgentNextStep,
    AgentRationaleCode,
    AgentRunStatus,
    AgentTokenUsage,
)


def _review(decision) -> AgentDecisionReview:
    evidence = decision.risk.evidence_references[0]
    evidence_id = f"{evidence.system}:{evidence.record_id}:{evidence.observed_at.isoformat()}"
    return AgentDecisionReview(
        decision_id=decision.decision_id,
        selected_action=decision.recommendation.selected_action,
        policy_disposition=decision.policy.disposition,
        next_step=AgentNextStep.SUBMIT_DECISION,
        rationale_codes=(
            AgentRationaleCode.HIGHEST_EXPECTED_VALUE,
            AgentRationaleCode.APPROVAL_REQUIRED,
        ),
        evidence_ids=(evidence_id,),
        requires_human_attention=True,
        uncertainty=0.1,
        summary="The selected recovery is supported by the immutable evidence.",
    )


def test_budget_reservation_completion_and_reuse(
    services,
    at_risk_request: EvaluationRequest,
) -> None:
    decision = services.evaluation.evaluate(at_risk_request)
    now = datetime.now(UTC)
    run, reused = services.openai_budget.reserve(
        decision_id=decision.decision_id,
        model="gpt-5-nano",
        prompt_version="test-v1",
        context_fingerprint="a" * 64,
        estimated_cost_usd=Decimal("0.000300"),
        now=now,
    )

    assert reused is False
    assert services.openai_budget.state().reserved_usd == Decimal("0.000300")

    completed = services.openai_budget.complete(
        run.run_id,
        usage=AgentTokenUsage(
            input_tokens=100,
            cached_input_tokens=0,
            output_tokens=20,
            total_tokens=120,
        ),
        actual_cost_usd=Decimal("0.000013"),
        response_id="resp-test",
        review=_review(decision),
        now=now + timedelta(seconds=1),
    )
    assert completed.status is AgentRunStatus.COMPLETED
    assert services.openai_budget.state().spent_usd == Decimal("0.000013")

    same, reused = services.openai_budget.reserve(
        decision_id=decision.decision_id,
        model="gpt-5-nano",
        prompt_version="test-v1",
        context_fingerprint="a" * 64,
        estimated_cost_usd=Decimal("0.000300"),
        now=now + timedelta(seconds=2),
    )
    assert reused is True
    assert same.run_id == completed.run_id


def test_per_run_and_project_guards_block_before_provider_call(
    services,
    at_risk_request: EvaluationRequest,
) -> None:
    decision = services.evaluation.evaluate(at_risk_request)
    manager = OpenAIBudgetManager(
        services.database,
        limit_usd=Decimal("0.001"),
        per_run_limit_usd=Decimal("0.001"),
    )

    with pytest.raises(OpenAIPerRunLimitError):
        manager.reserve(
            decision_id=decision.decision_id,
            model="gpt-5-nano",
            prompt_version="test-v1",
            context_fingerprint="b" * 64,
            estimated_cost_usd=Decimal("0.001001"),
        )

    manager.reserve(
        decision_id=decision.decision_id,
        model="gpt-5-nano",
        prompt_version="test-v1",
        context_fingerprint="c" * 64,
        estimated_cost_usd=Decimal("0.001000"),
    )
    with pytest.raises(OpenAIBudgetExceededError):
        manager.reserve(
            decision_id=decision.decision_id,
            model="gpt-5-nano",
            prompt_version="test-v1",
            context_fingerprint="d" * 64,
            estimated_cost_usd=Decimal("0.000001"),
        )


def test_stale_reservation_is_charged_conservatively(
    services,
    at_risk_request: EvaluationRequest,
) -> None:
    decision = services.evaluation.evaluate(at_risk_request)
    now = datetime.now(UTC)
    manager = OpenAIBudgetManager(
        services.database,
        limit_usd=Decimal("3.00"),
        per_run_limit_usd=Decimal("0.001"),
        reservation_ttl=timedelta(seconds=1),
    )
    run, _ = manager.reserve(
        decision_id=decision.decision_id,
        model="gpt-5-nano",
        prompt_version="stale-v1",
        context_fingerprint="e" * 64,
        estimated_cost_usd=Decimal("0.000250"),
        now=now,
    )

    state = manager.state(now=now + timedelta(seconds=2))
    persisted = manager.get(run.run_id)

    assert state.reserved_usd == Decimal("0")
    assert state.spent_usd >= Decimal("0.000250")
    assert persisted is not None
    assert persisted.status is AgentRunStatus.FAILED
    assert persisted.error_code == "STALE_RESERVATION_CHARGED_CONSERVATIVELY"
