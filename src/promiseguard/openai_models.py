"""Strict contracts for the bounded OpenAI orchestration layer."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from promiseguard.models import (
    PolicyDisposition,
    RecoveryAction,
    StrictModel,
    WorkflowState,
)

NonNegativeCost = Annotated[Decimal, Field(ge=Decimal("0"))]


class AgentRationaleCode(str, Enum):
    HIGHEST_EXPECTED_VALUE = "HIGHEST_EXPECTED_VALUE"
    REVERSIBLE_ACTION = "REVERSIBLE_ACTION"
    WITHIN_POLICY = "WITHIN_POLICY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    BOUNDED_AUTONOMY_ALLOWED = "BOUNDED_AUTONOMY_ALLOWED"
    NO_POSITIVE_VALUE = "NO_POSITIVE_VALUE"
    DATA_QUALITY_WARNING = "DATA_QUALITY_WARNING"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    HUMAN_ESCALATION = "HUMAN_ESCALATION"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"


class AgentNextStep(str, Enum):
    SUBMIT_DECISION = "SUBMIT_DECISION"
    WAIT_FOR_HUMAN = "WAIT_FOR_HUMAN"
    ESCALATE = "ESCALATE"
    NO_ACTION = "NO_ACTION"


class AgentRunStatus(str, Enum):
    RESERVED = "RESERVED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    BUDGET_BLOCKED = "BUDGET_BLOCKED"


class AgentDecisionReview(StrictModel):
    """Model-authored intent that must pass deterministic validation."""

    decision_id: str = Field(min_length=1, max_length=64)
    selected_action: RecoveryAction
    policy_disposition: PolicyDisposition
    next_step: AgentNextStep
    rationale_codes: tuple[AgentRationaleCode, ...] = Field(min_length=1, max_length=6)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=20)
    requires_human_attention: bool
    uncertainty: Annotated[float, Field(ge=0.0, le=1.0)]
    summary: str = Field(min_length=8, max_length=420)

    @field_validator("summary")
    @classmethod
    def summary_must_not_make_numeric_claims(cls, value: str) -> str:
        forbidden = set("0123456789$£€¥")
        if any(character in forbidden for character in value):
            raise ValueError("summary must not contain numeric or currency claims")
        return value.strip()

    @model_validator(mode="after")
    def evidence_ids_must_be_unique(self) -> AgentDecisionReview:
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence_ids must be unique")
        if len(set(self.rationale_codes)) != len(self.rationale_codes):
            raise ValueError("rationale_codes must be unique")
        return self


class AgentRunRequest(StrictModel):
    decision_id: str = Field(min_length=1, max_length=64)
    actor_id: str = Field(min_length=1, max_length=120)
    advance_workflow: bool = False


class AgentTokenUsage(StrictModel):
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def total_must_cover_components(self) -> AgentTokenUsage:
        if self.total_tokens < self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens cannot be lower than input plus output")
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached_input_tokens cannot exceed input_tokens")
        return self


class AgentBudgetState(StrictModel):
    budget_key: str
    limit_usd: NonNegativeCost
    reserved_usd: NonNegativeCost
    spent_usd: NonNegativeCost
    remaining_usd: NonNegativeCost
    updated_at: datetime
    version: int = Field(ge=1)


class AgentRunRecord(StrictModel):
    run_id: str
    request_key: str
    decision_id: str
    model: str
    prompt_version: str
    status: AgentRunStatus
    context_fingerprint: str
    reserved_cost_usd: NonNegativeCost
    actual_cost_usd: NonNegativeCost
    usage: AgentTokenUsage | None = None
    response_id: str | None = None
    review: AgentDecisionReview | None = None
    created_at: datetime
    completed_at: datetime | None = None
    error_code: str | None = None
    validation_errors: tuple[str, ...] = ()


class AgentRunResult(StrictModel):
    run: AgentRunRecord
    budget: AgentBudgetState
    workflow: WorkflowState | None = None
    reused_existing_run: bool = False
