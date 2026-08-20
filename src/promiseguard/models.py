"""Typed domain contracts for the first PromiseGuard vertical slice."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Probability = Annotated[float, Field(ge=0.0, le=1.0)]
NonNegativeMoney = Annotated[Decimal, Field(ge=Decimal("0"))]


class StrictModel(BaseModel):
    """Base model that rejects unknown fields and validates assignments."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True, frozen=True)


class OperatingMode(str, Enum):
    OBSERVE = "OBSERVE"
    SHADOW = "SHADOW"
    RECOMMENDATION = "RECOMMENDATION"
    APPROVAL = "APPROVAL"
    BOUNDED_AUTONOMY = "BOUNDED_AUTONOMY"


class RecoveryAction(str, Enum):
    TAKE_NO_ACTION = "TAKE_NO_ACTION"
    REROUTE = "REROUTE"
    CARRIER_UPGRADE = "CARRIER_UPGRADE"


class PolicyDisposition(str, Enum):
    AUTO_EXECUTE = "AUTO_EXECUTE"
    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    ESCALATE = "ESCALATE"
    BLOCK = "BLOCK"
    TAKE_NO_ACTION = "TAKE_NO_ACTION"


class DecisionStatus(str, Enum):
    OBSERVED = "OBSERVED"
    SHADOW_RECORDED = "SHADOW_RECORDED"
    RECOMMENDED = "RECOMMENDED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTION_NOT_IMPLEMENTED = "EXECUTION_NOT_IMPLEMENTED"


class SourceReference(StrictModel):
    system: str = Field(min_length=1, max_length=80)
    record_id: str = Field(min_length=1, max_length=120)
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value


class OperationalEvent(StrictModel):
    source_system: str = Field(min_length=1, max_length=80)
    event_id: str = Field(min_length=1, max_length=120)
    event_version: int = Field(ge=1)
    event_type: str = Field(min_length=1, max_length=100)
    event_time: datetime
    ingestion_time: datetime
    schema_version: str = Field(pattern=r"^v\d+$")
    deduplication_key: str = Field(min_length=1, max_length=180)

    @field_validator("event_time", "ingestion_time")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event timestamps must be timezone-aware")
        return value


class OrderContext(StrictModel):
    order_id: str = Field(min_length=1, max_length=120)
    evaluation_time: datetime
    promised_delivery_at: datetime
    gross_margin: NonNegativeMoney
    cancellation_cost: NonNegativeMoney
    support_cost: NonNegativeMoney
    inventory_reserved: bool
    inventory_available: bool
    inventory_confidence: Probability
    carrier_on_time_probability: Probability
    hours_since_expected_scan: float = Field(ge=0.0, le=240.0)
    alternative_location_available: bool
    reroute_on_time_probability: Probability
    carrier_upgrade_on_time_probability: Probability
    reroute_cost: NonNegativeMoney
    carrier_upgrade_cost: NonNegativeMoney
    data_freshness_minutes: int = Field(ge=0, le=10_080)
    source_references: tuple[SourceReference, ...] = Field(min_length=1)
    external_notes: str | None = Field(default=None, max_length=2_000)

    @field_validator("evaluation_time", "promised_delivery_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("order timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_temporal_order(self) -> OrderContext:
        if self.promised_delivery_at <= self.evaluation_time:
            raise ValueError("promised_delivery_at must be after evaluation_time")
        return self


class EvaluationRequest(StrictModel):
    event: OperationalEvent
    order: OrderContext
    mode: OperatingMode = OperatingMode.SHADOW

    @model_validator(mode="after")
    def validate_event_order_alignment(self) -> EvaluationRequest:
        if self.event.ingestion_time > self.order.evaluation_time:
            raise ValueError("evaluation_time cannot precede event ingestion_time")
        return self


class RiskFactor(StrictModel):
    code: str
    contribution: float
    explanation: str


class RiskAssessment(StrictModel):
    failure_probability: Probability
    confidence: Probability
    model_version: str
    feature_timestamp: datetime
    factors: tuple[RiskFactor, ...]
    data_quality_warnings: tuple[str, ...] = ()
    evidence_references: tuple[SourceReference, ...]


class RecoveryOption(StrictModel):
    action: RecoveryAction
    feasible: bool
    on_time_probability: Probability
    expected_retained_gross_margin: Decimal
    intervention_cost: NonNegativeMoney
    expected_failure_cost: NonNegativeMoney
    expected_net_value: Decimal
    reversible: bool
    confidence: Probability
    constraints: tuple[str, ...] = ()
    evidence_references: tuple[SourceReference, ...]


class DecisionRecommendation(StrictModel):
    selected_action: RecoveryAction
    ranked_options: tuple[RecoveryOption, ...]
    expected_incremental_value_vs_no_action: Decimal
    rejected_options: tuple[str, ...] = ()
    confidence: Probability


class PolicyEvaluation(StrictModel):
    disposition: PolicyDisposition
    policy_version: str
    execution_allowed: bool
    reasons: tuple[str, ...]


class DecisionTrace(StrictModel):
    trace_version: str
    decision_id: str
    event_id: str
    order_id: str
    mode: OperatingMode
    risk: RiskAssessment
    recommendation: DecisionRecommendation
    policy: PolicyEvaluation
    status: DecisionStatus
    created_at: datetime
