"""Strict, vendor-neutral contracts for OMS, WMS and carrier adapters.

Decision, optimisation and policy code must depend only on these contracts.
Vendor SDKs and HTTP clients belong behind sandbox or future live adapters.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import Field

from promiseguard.adapters.errors import AdapterErrorClass
from promiseguard.models import (
    ActionExecution,
    OrderContext,
    RecoveryAction,
    StrictModel,
)

ADAPTER_CONTRACT_VERSION = "v1"
DEFAULT_TENANT_ID = "local-default"


class TimeoutPolicy(StrictModel):
    request_timeout_seconds: float = Field(gt=0.0, le=120.0)
    verification_timeout_seconds: float = Field(gt=0.0, le=120.0)


class RetryPolicy(StrictModel):
    """Retry policy for adapter calls.

    Ambiguous write outcomes are never retried blindly. The gateway must verify
    the postcondition before considering another attempt.
    """

    max_attempts: int = Field(ge=1, le=5)
    retry_on: tuple[AdapterErrorClass, ...] = ()
    backoff_seconds: float = Field(ge=0.0, le=30.0)


class IdempotencySemantics(StrictModel):
    key_scope: str
    reuse_same_operation: str
    reuse_different_operation: str
    verification_after_timeout: str


class AdapterObservability(StrictModel):
    correlation_header: str = "X-Correlation-ID"
    log_fields: tuple[str, ...] = (
        "system",
        "operation",
        "error_class",
        "provider_reference",
        "duration_seconds",
    )
    metric_names: tuple[str, ...] = (
        "promiseguard_adapter_calls_total",
        "promiseguard_adapter_latency_seconds",
    )


class AdapterContract(StrictModel):
    system: str = Field(pattern=r"^(oms|wms|carrier)$")
    contract_version: str = ADAPTER_CONTRACT_VERSION
    operations: tuple[str, ...]
    authentication_boundary: str
    timeout: TimeoutPolicy
    retry: RetryPolicy
    idempotency: IdempotencySemantics
    expected_postconditions: tuple[str, ...]
    ambiguous_outcome_handling: str
    compensating_actions: tuple[str, ...]
    rate_limit_per_minute: int | None = Field(default=None, ge=1)
    observability: AdapterObservability = AdapterObservability()
    error_classes: tuple[AdapterErrorClass, ...]
    audit_evidence: tuple[str, ...]
    versioning: str


class AdapterRequestMeta(StrictModel):
    correlation_id: str = Field(min_length=8, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=180)
    tenant_id: str = Field(default=DEFAULT_TENANT_ID, min_length=1, max_length=80)
    actor_id: str | None = Field(default=None, max_length=120)
    contract_version: str = ADAPTER_CONTRACT_VERSION


class AdapterResponseMeta(StrictModel):
    correlation_id: str = Field(min_length=8, max_length=128)
    provider_reference: str = Field(min_length=1, max_length=240)
    contract_version: str = ADAPTER_CONTRACT_VERSION
    error_class: AdapterErrorClass = AdapterErrorClass.SUCCESS
    retryable: bool = False
    ambiguous: bool = False


class WmsReserveRequest(StrictModel):
    meta: AdapterRequestMeta
    order_id: str = Field(min_length=1, max_length=120)
    sku: str = Field(min_length=1, max_length=120)
    quantity: int = Field(ge=1, le=10_000)
    location_id: str = Field(min_length=1, max_length=80)


class WmsReserveResponse(StrictModel):
    meta: AdapterResponseMeta
    reservation_id: str
    location_id: str
    sku: str
    quantity: int


class WmsReleaseRequest(StrictModel):
    meta: AdapterRequestMeta
    order_id: str = Field(min_length=1, max_length=120)
    location_id: str | None = Field(default=None, max_length=80)


class WmsReleaseResponse(StrictModel):
    meta: AdapterResponseMeta
    released: bool


class OmsChangeLocationRequest(StrictModel):
    meta: AdapterRequestMeta
    order_id: str = Field(min_length=1, max_length=120)
    from_location: str = Field(min_length=1, max_length=80)
    to_location: str = Field(min_length=1, max_length=80)


class OmsChangeLocationResponse(StrictModel):
    meta: AdapterResponseMeta
    order_id: str
    location_id: str


class OmsSplitRequest(StrictModel):
    meta: AdapterRequestMeta
    order_id: str = Field(min_length=1, max_length=120)
    quantity: int = Field(ge=1, le=10_000)


class OmsSplitResponse(StrictModel):
    meta: AdapterResponseMeta
    order_id: str
    split: bool


class CarrierUpgradeRequest(StrictModel):
    meta: AdapterRequestMeta
    order_id: str = Field(min_length=1, max_length=120)
    from_service: str = Field(min_length=1, max_length=80)
    to_service: str = Field(min_length=1, max_length=80)


class CarrierUpgradeResponse(StrictModel):
    meta: AdapterResponseMeta
    order_id: str
    service: str


class DeliveryOutcomeRequest(StrictModel):
    meta: AdapterRequestMeta
    order_id: str = Field(min_length=1, max_length=120)
    delivered_on_time: bool


class DeliveryOutcomeResponse(StrictModel):
    meta: AdapterResponseMeta
    order_id: str
    delivered_on_time: bool


WMS_CONTRACT = AdapterContract(
    system="wms",
    operations=("reserve_alternative", "release_alternative"),
    authentication_boundary=(
        "Service identity authenticates to WMS. Core decision logic never holds "
        "WMS credentials and never issues raw WMS commands."
    ),
    timeout=TimeoutPolicy(request_timeout_seconds=5.0, verification_timeout_seconds=5.0),
    retry=RetryPolicy(
        max_attempts=1,
        retry_on=(),
        backoff_seconds=0.0,
    ),
    idempotency=IdempotencySemantics(
        key_scope="wms-reservation-per-order-location",
        reuse_same_operation="return-cached-provider-reference",
        reuse_different_operation="conflict",
        verification_after_timeout="read-reservation-postcondition-before-retry",
    ),
    expected_postconditions=(
        "reservation exists for (order_id, alternative_location_id)",
        "release removes that reservation",
    ),
    ambiguous_outcome_handling=(
        "Timeouts after a possible write are classified AMBIGUOUS. The gateway "
        "verifies the reservation before completing or compensating."
    ),
    compensating_actions=("release_alternative",),
    rate_limit_per_minute=120,
    error_classes=tuple(AdapterErrorClass),
    audit_evidence=(
        "idempotency_key",
        "correlation_id",
        "provider_reference",
        "error_class",
    ),
    versioning="contract v1; additive response fields only",
)

OMS_CONTRACT = AdapterContract(
    system="oms",
    operations=("change_location", "restore_location", "create_split", "cancel_split"),
    authentication_boundary=(
        "Service identity authenticates to OMS. Fulfilment mutations occur only "
        "through the governed action gateway."
    ),
    timeout=TimeoutPolicy(request_timeout_seconds=5.0, verification_timeout_seconds=5.0),
    retry=RetryPolicy(max_attempts=1, retry_on=(), backoff_seconds=0.0),
    idempotency=IdempotencySemantics(
        key_scope="oms-mutation-per-order-action",
        reuse_same_operation="return-cached-provider-reference",
        reuse_different_operation="conflict",
        verification_after_timeout="read-order-postcondition-before-retry",
    ),
    expected_postconditions=(
        "reroute: order location equals alternative_location_id",
        "split: split-shipment flag is present for the order",
        "restore/cancel returns the order to the pre-action state",
    ),
    ambiguous_outcome_handling=(
        "Lost acknowledgements are treated as ambiguous. Success is recorded "
        "only after an independent postcondition read."
    ),
    compensating_actions=("restore_location", "cancel_split"),
    rate_limit_per_minute=120,
    error_classes=tuple(AdapterErrorClass),
    audit_evidence=(
        "idempotency_key",
        "correlation_id",
        "provider_reference",
        "error_class",
    ),
    versioning="contract v1; additive response fields only",
)

CARRIER_CONTRACT = AdapterContract(
    system="carrier",
    operations=("upgrade_carrier", "restore_carrier", "record_delivery_outcome"),
    authentication_boundary=(
        "Service identity authenticates to the carrier API. Tracking reads used "
        "for outcome verification are independent from the upgrade write."
    ),
    timeout=TimeoutPolicy(request_timeout_seconds=8.0, verification_timeout_seconds=8.0),
    retry=RetryPolicy(max_attempts=1, retry_on=(), backoff_seconds=0.0),
    idempotency=IdempotencySemantics(
        key_scope="carrier-service-change-per-order",
        reuse_same_operation="return-cached-provider-reference",
        reuse_different_operation="conflict",
        verification_after_timeout="read-carrier-service-postcondition-before-retry",
    ),
    expected_postconditions=(
        "upgrade: recorded service equals upgraded_carrier_service",
        "restore: recorded service equals current_carrier_service",
    ),
    ambiguous_outcome_handling=(
        "Timeouts after a possible service change are verified against the "
        "carrier record before retry or compensation."
    ),
    compensating_actions=("restore_carrier",),
    rate_limit_per_minute=60,
    error_classes=tuple(AdapterErrorClass),
    audit_evidence=(
        "idempotency_key",
        "correlation_id",
        "provider_reference",
        "error_class",
    ),
    versioning="contract v1; additive response fields only",
)


class WmsAdapter(Protocol):
    def reserve_inventory(self, request: WmsReserveRequest) -> WmsReserveResponse: ...

    def release_inventory(self, request: WmsReleaseRequest) -> WmsReleaseResponse: ...


class OmsAdapter(Protocol):
    def change_fulfilment_location(
        self, request: OmsChangeLocationRequest
    ) -> OmsChangeLocationResponse: ...

    def restore_fulfilment_location(
        self, request: OmsChangeLocationRequest
    ) -> OmsChangeLocationResponse: ...

    def create_split_shipment(self, request: OmsSplitRequest) -> OmsSplitResponse: ...

    def cancel_split_shipment(self, request: OmsSplitRequest) -> OmsSplitResponse: ...


class CarrierAdapter(Protocol):
    def upgrade_service(self, request: CarrierUpgradeRequest) -> CarrierUpgradeResponse: ...

    def restore_service(self, request: CarrierUpgradeRequest) -> CarrierUpgradeResponse: ...

    def record_delivery(self, request: DeliveryOutcomeRequest) -> DeliveryOutcomeResponse: ...


class OperationsPort(Protocol):
    """Facade used by the action gateway and outcome verification.

    Live OMS/WMS/carrier clients must implement the typed adapters above. The
    sandbox composite implements this port so the gateway stays vendor-neutral.
    """

    def seed_order(self, order: OrderContext) -> None: ...

    def inject_failure(self, step_name: str, *, when: str = "before") -> None: ...

    def clear_failures(self) -> None: ...

    def record_delivery_outcome(self, order_id: str, *, delivered_on_time: bool) -> None: ...

    def reserve_alternative(self, *, order: OrderContext, idempotency_key: str) -> str: ...

    def release_alternative(self, *, order: OrderContext) -> str: ...

    def change_location(self, *, order: OrderContext, idempotency_key: str) -> str: ...

    def restore_location(self, *, order: OrderContext) -> str: ...

    def upgrade_carrier(self, *, order: OrderContext, idempotency_key: str) -> str: ...

    def restore_carrier(self, *, order: OrderContext) -> str: ...

    def create_split(self, *, order: OrderContext, idempotency_key: str) -> str: ...

    def cancel_split(self, *, order: OrderContext) -> str: ...

    def action_postcondition_holds(
        self, *, order: OrderContext, action: RecoveryAction
    ) -> bool: ...

    def hydrate_from_durable_action(
        self, *, order: OrderContext, execution: ActionExecution
    ) -> None: ...
