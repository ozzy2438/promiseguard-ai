"""Typed domain contracts for PromiseGuard decisions and governed execution."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Probability = Annotated[float, Field(ge=0.0, le=1.0)]
NonNegativeMoney = Annotated[Decimal, Field(ge=Decimal("0"))]
PositiveQuantity = Annotated[int, Field(ge=1, le=10_000)]


class StrictModel(BaseModel):
    """Base model that rejects unknown fields and validates assignments."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True, frozen=True)


class OperatingMode(StrEnum):
    OBSERVE = "OBSERVE"
    SHADOW = "SHADOW"
    RECOMMENDATION = "RECOMMENDATION"
    APPROVAL = "APPROVAL"
    BOUNDED_AUTONOMY = "BOUNDED_AUTONOMY"


class RecoveryAction(StrEnum):
    TAKE_NO_ACTION = "TAKE_NO_ACTION"
    REROUTE = "REROUTE"
    CARRIER_UPGRADE = "CARRIER_UPGRADE"
    SPLIT_SHIPMENT = "SPLIT_SHIPMENT"
    HUMAN_ESCALATION = "HUMAN_ESCALATION"


class PolicyDisposition(StrEnum):
    AUTO_EXECUTE = "AUTO_EXECUTE"
    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    ESCALATE = "ESCALATE"
    BLOCK = "BLOCK"
    TAKE_NO_ACTION = "TAKE_NO_ACTION"


class DecisionStatus(StrEnum):
    OBSERVED = "OBSERVED"
    SHADOW_RECORDED = "SHADOW_RECORDED"
    RECOMMENDED = "RECOMMENDED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    READY_FOR_EXECUTION = "READY_FOR_EXECUTION"
    EXECUTION_NOT_IMPLEMENTED = "EXECUTION_NOT_IMPLEMENTED"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ActionStatus(StrEnum):
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    VERIFIED = "VERIFIED"
    COMPENSATED = "COMPENSATED"
    FAILED = "FAILED"
    MANUAL_RECOVERY_REQUIRED = "MANUAL_RECOVERY_REQUIRED"


class StepStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    COMPENSATED = "COMPENSATED"
    SKIPPED = "SKIPPED"


class VerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


class UserRole(StrEnum):
    OPERATIONS_ANALYST = "OPERATIONS_ANALYST"
    OPERATIONS_MANAGER = "OPERATIONS_MANAGER"
    AUDITOR = "AUDITOR"
    SERVICE_IDENTITY = "SERVICE_IDENTITY"


class AutonomyLevel(StrEnum):
    OBSERVE = "OBSERVE"
    RECOMMEND = "RECOMMEND"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    BOUNDED_AUTONOMY = "BOUNDED_AUTONOMY"
    SUSPENDED = "SUSPENDED"


class SyntheticEventAnomaly(StrEnum):
    NONE = "NONE"
    DUPLICATE = "DUPLICATE"
    LATE_ARRIVAL = "LATE_ARRIVAL"
    OUT_OF_ORDER = "OUT_OF_ORDER"


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
    customer_id: str = Field(default="customer-unknown", min_length=1, max_length=120)
    customer_segment: str = Field(default="STANDARD", min_length=1, max_length=40)
    currency: str = Field(default="AUD", pattern=r"^[A-Z]{3}$")
    sku: str = Field(default="SKU-UNKNOWN", min_length=1, max_length=120)
    quantity: PositiveQuantity = 1
    current_fulfilment_location: str = Field(default="FC-MEL", min_length=1, max_length=80)
    alternative_location_id: str | None = Field(default=None, max_length=80)
    current_carrier_service: str = Field(default="STANDARD", min_length=1, max_length=80)
    upgraded_carrier_service: str = Field(default="EXPRESS", min_length=1, max_length=80)
    split_shipment_possible: bool = False
    split_shipment_on_time_probability: Probability = 0.0
    split_shipment_cost: NonNegativeMoney = Decimal("0")
    restricted_product: bool = False

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
        if self.alternative_location_id == self.current_fulfilment_location:
            raise ValueError("alternative_location_id must differ from current location")
        if self.split_shipment_possible and self.split_shipment_on_time_probability <= 0:
            raise ValueError("split probability must be positive when split is possible")
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
    control_version: str
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


class ApprovalRecord(StrictModel):
    approval_id: str
    decision_id: str
    requested_action: RecoveryAction
    status: ApprovalStatus
    requested_by: str
    requested_at: datetime
    expires_at: datetime
    decided_by: str | None = None
    decided_by_role: UserRole | None = None
    decision_reason: str | None = None
    decided_at: datetime | None = None


class ApprovalDecisionInput(StrictModel):
    actor_id: str = Field(min_length=1, max_length=120)
    actor_role: UserRole
    reason: str = Field(min_length=3, max_length=500)


class SubmitDecisionInput(StrictModel):
    actor_id: str = Field(min_length=1, max_length=120)


class ActionCommand(StrictModel):
    decision_id: str
    order_id: str
    action: RecoveryAction
    idempotency_key: str = Field(min_length=8, max_length=180)
    requested_by: str
    approved_by: str | None = None
    expected_intervention_cost: NonNegativeMoney
    parameters: dict[str, Any]


class ActionStepResult(StrictModel):
    sequence: int = Field(ge=1)
    step_name: str
    status: StepStatus
    attempted_at: datetime
    completed_at: datetime | None = None
    provider_reference: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None


class ActionExecution(StrictModel):
    action_id: str
    command: ActionCommand
    status: ActionStatus
    steps: tuple[ActionStepResult, ...]
    started_at: datetime
    completed_at: datetime | None = None
    error_code: str | None = None
    manual_recovery_reason: str | None = None


class DeliveryObservation(StrictModel):
    order_id: str = Field(min_length=1, max_length=120)
    delivered_on_time: bool
    observed_at: datetime
    source_reference: SourceReference

    @field_validator("observed_at")
    @classmethod
    def require_observation_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value


class OutcomeVerification(StrictModel):
    outcome_id: str
    decision_id: str
    action_id: str
    status: VerificationStatus
    verified_at: datetime
    on_time_delivery_observed: bool | None
    actual_intervention_cost: NonNegativeMoney
    realised_gross_margin: Decimal
    estimated_incremental_value: Decimal
    evidence_references: tuple[SourceReference, ...]
    details: dict[str, Any] = Field(default_factory=dict)


class WorkflowState(StrictModel):
    decision: DecisionTrace
    approval: ApprovalRecord | None = None
    execution: ActionExecution | None = None
    outcome: OutcomeVerification | None = None


class KillSwitchState(StrictModel):
    active: bool
    reason: str
    updated_by: str
    updated_at: datetime
    version: int = Field(ge=1)

    @field_validator("updated_at")
    @classmethod
    def require_updated_at_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("updated_at must be timezone-aware")
        return value


class KillSwitchUpdateInput(StrictModel):
    active: bool
    actor_id: str = Field(min_length=1, max_length=120)
    actor_role: UserRole
    reason: str = Field(min_length=3, max_length=500)


class AutonomyProfile(StrictModel):
    action: RecoveryAction
    level: AutonomyLevel
    verified_successes: int = Field(ge=0)
    consecutive_verified_successes: int = Field(ge=0)
    compensation_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    recommended_for_promotion: bool
    reason: str
    last_evidence_at: datetime | None = None
    updated_by: str
    updated_at: datetime
    version: int = Field(ge=1)

    @field_validator("last_evidence_at", "updated_at")
    @classmethod
    def require_control_timestamp_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("autonomy timestamps must be timezone-aware")
        return value


class AutonomyUpdateInput(StrictModel):
    level: AutonomyLevel
    actor_id: str = Field(min_length=1, max_length=120)
    actor_role: UserRole
    reason: str = Field(min_length=3, max_length=500)


class SyntheticGroundTruth(StrictModel):
    no_action_on_time_probability: Probability
    reroute_on_time_probability: Probability
    carrier_upgrade_on_time_probability: Probability
    split_shipment_on_time_probability: Probability
    sampled_no_action_failure: bool
    optimal_action: RecoveryAction


class SyntheticRecord(StrictModel):
    request: EvaluationRequest
    ground_truth: SyntheticGroundTruth


class SyntheticEventEnvelope(StrictModel):
    order_id: str = Field(min_length=1, max_length=120)
    event_sequence: int = Field(ge=1)
    emission_sequence: int = Field(ge=1)
    event: OperationalEvent
    payload: dict[str, Any]
    anomaly: SyntheticEventAnomaly = SyntheticEventAnomaly.NONE
    duplicate_of: str | None = None

    @model_validator(mode="after")
    def validate_duplicate_reference(self) -> SyntheticEventEnvelope:
        if self.anomaly is SyntheticEventAnomaly.DUPLICATE and not self.duplicate_of:
            raise ValueError("duplicate event must reference the original event id")
        if self.anomaly is not SyntheticEventAnomaly.DUPLICATE and self.duplicate_of:
            raise ValueError("only duplicate events may set duplicate_of")
        return self
