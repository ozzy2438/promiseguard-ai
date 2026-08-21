"""Sandbox OMS, WMS and carrier adapters behind a vendor-neutral operations port.

These adapters are production-grade contracts with in-process systems of record.
They are not live retailer integrations. Failure injection exists so timeout,
malformed, rate-limit and compensation paths can be proven locally.
"""

from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4

from promiseguard.adapters.contracts import (
    ADAPTER_CONTRACT_VERSION,
    AdapterRequestMeta,
    AdapterResponseMeta,
    CarrierUpgradeRequest,
    CarrierUpgradeResponse,
    DeliveryOutcomeRequest,
    DeliveryOutcomeResponse,
    OmsChangeLocationRequest,
    OmsChangeLocationResponse,
    OmsSplitRequest,
    OmsSplitResponse,
    WmsReleaseRequest,
    WmsReleaseResponse,
    WmsReserveRequest,
    WmsReserveResponse,
)
from promiseguard.adapters.errors import (
    ActionExecutionError,
    AdapterErrorClass,
    AdapterRateLimited,
    AmbiguousProviderTimeout,
    MalformedAdapterResponse,
)
from promiseguard.models import ActionExecution, ActionStatus, OrderContext, RecoveryAction
from promiseguard.observability import current_correlation_id
from promiseguard.persistence import PersistenceConflictError

_FAILURE_MODES = {"before", "after", "malformed", "rate_limited", "hard_after"}
_LOGGER = logging.getLogger("promiseguard.adapters")


class _SandboxState:
    def __init__(self) -> None:
        self.order_locations: dict[str, str] = {}
        self.carrier_services: dict[str, str] = {}
        self.split_shipments: set[str] = set()
        self.alternative_reservations: set[tuple[str, str]] = set()
        self.delivery_outcomes: dict[str, bool] = {}
        self.applied_idempotency_keys: dict[str, str] = {}
        self.failure_modes: dict[str, str] = {}


def _meta(
    *,
    correlation_id: str,
    provider_reference: str,
    error_class: AdapterErrorClass = AdapterErrorClass.SUCCESS,
    retryable: bool = False,
    ambiguous: bool = False,
) -> AdapterResponseMeta:
    return AdapterResponseMeta(
        correlation_id=correlation_id,
        provider_reference=provider_reference,
        contract_version=ADAPTER_CONTRACT_VERSION,
        error_class=error_class,
        retryable=retryable,
        ambiguous=ambiguous,
    )


class SharedSandboxRuntime:
    """In-memory systems-of-record used by the three sandbox adapters."""

    def __init__(self, state: _SandboxState | None = None) -> None:
        self.state = state or _SandboxState()

    def seed_order(self, order: OrderContext) -> None:
        self.state.order_locations.setdefault(order.order_id, order.current_fulfilment_location)
        self.state.carrier_services.setdefault(order.order_id, order.current_carrier_service)

    def inject_failure(self, step_name: str, *, when: str = "before") -> None:
        if when not in _FAILURE_MODES:
            raise ValueError("failure timing must be one of " + ", ".join(sorted(_FAILURE_MODES)))
        self.state.failure_modes[step_name] = when

    def clear_failures(self) -> None:
        self.state.failure_modes.clear()

    def claim_key(self, key: str, operation: str) -> None:
        existing = self.state.applied_idempotency_keys.get(key)
        if existing is not None and existing != operation:
            raise PersistenceConflictError(
                "provider idempotency key was reused for a different operation"
            )
        self.state.applied_idempotency_keys[key] = operation

    def before(self, step: str) -> None:
        mode = self.state.failure_modes.get(step)
        if mode == "before":
            raise ActionExecutionError(f"injected failure before {step}")
        if mode == "rate_limited":
            raise AdapterRateLimited(f"injected rate limit before {step}")

    def after(self, step: str) -> None:
        mode = self.state.failure_modes.get(step)
        if mode == "after":
            raise AmbiguousProviderTimeout(f"injected timeout after {step}")
        if mode == "malformed":
            raise MalformedAdapterResponse(f"injected malformed response after {step}")
        if mode == "hard_after":
            raise ActionExecutionError(f"injected hard failure after {step}")

    def request_meta(
        self, idempotency_key: str, *, tenant_id: str, actor_id: str | None
    ) -> AdapterRequestMeta:
        return AdapterRequestMeta(
            correlation_id=current_correlation_id()
            if current_correlation_id() != "-"
            else f"corr_{uuid4().hex}",
            idempotency_key=idempotency_key,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )

    def log_call(self, *, system: str, operation: str, reference: str, started: float) -> None:
        _LOGGER.info(
            "adapter_call",
            extra={
                "system": system,
                "operation": operation,
                "error_class": AdapterErrorClass.SUCCESS.value,
                "provider_reference": reference,
                "duration_seconds": perf_counter() - started,
            },
        )


class SandboxWmsAdapter:
    def __init__(self, runtime: SharedSandboxRuntime) -> None:
        self.runtime = runtime

    def reserve_inventory(self, request: WmsReserveRequest) -> WmsReserveResponse:
        started = perf_counter()
        step = "reserve_alternative"
        self.runtime.before(step)
        self.runtime.claim_key(
            request.meta.idempotency_key,
            f"reserve:{request.order_id}:{request.location_id}",
        )
        self.runtime.state.alternative_reservations.add((request.order_id, request.location_id))
        self.runtime.after(step)
        reference = f"reservation:{request.order_id}:{request.location_id}"
        self.runtime.log_call(system="wms", operation=step, reference=reference, started=started)
        return WmsReserveResponse(
            meta=_meta(correlation_id=request.meta.correlation_id, provider_reference=reference),
            reservation_id=reference,
            location_id=request.location_id,
            sku=request.sku,
            quantity=request.quantity,
        )

    def release_inventory(self, request: WmsReleaseRequest) -> WmsReleaseResponse:
        if request.location_id is not None:
            self.runtime.state.alternative_reservations.discard(
                (request.order_id, request.location_id)
            )
        reference = f"released:{request.order_id}"
        return WmsReleaseResponse(
            meta=_meta(correlation_id=request.meta.correlation_id, provider_reference=reference),
            released=True,
        )


class SandboxOmsAdapter:
    def __init__(self, runtime: SharedSandboxRuntime) -> None:
        self.runtime = runtime

    def change_fulfilment_location(
        self, request: OmsChangeLocationRequest
    ) -> OmsChangeLocationResponse:
        started = perf_counter()
        step = "change_location"
        self.runtime.before(step)
        self.runtime.claim_key(
            request.meta.idempotency_key,
            f"reroute:{request.order_id}:{request.to_location}",
        )
        self.runtime.state.order_locations[request.order_id] = request.to_location
        self.runtime.after(step)
        reference = f"order-location:{request.order_id}:{request.to_location}"
        self.runtime.log_call(system="oms", operation=step, reference=reference, started=started)
        return OmsChangeLocationResponse(
            meta=_meta(correlation_id=request.meta.correlation_id, provider_reference=reference),
            order_id=request.order_id,
            location_id=request.to_location,
        )

    def restore_fulfilment_location(
        self, request: OmsChangeLocationRequest
    ) -> OmsChangeLocationResponse:
        self.runtime.state.order_locations[request.order_id] = request.from_location
        reference = f"restored-location:{request.order_id}:{request.from_location}"
        return OmsChangeLocationResponse(
            meta=_meta(correlation_id=request.meta.correlation_id, provider_reference=reference),
            order_id=request.order_id,
            location_id=request.from_location,
        )

    def create_split_shipment(self, request: OmsSplitRequest) -> OmsSplitResponse:
        started = perf_counter()
        step = "create_split"
        self.runtime.before(step)
        self.runtime.claim_key(request.meta.idempotency_key, f"split:{request.order_id}")
        self.runtime.state.split_shipments.add(request.order_id)
        self.runtime.after(step)
        reference = f"split-shipment:{request.order_id}"
        self.runtime.log_call(system="oms", operation=step, reference=reference, started=started)
        return OmsSplitResponse(
            meta=_meta(correlation_id=request.meta.correlation_id, provider_reference=reference),
            order_id=request.order_id,
            split=True,
        )

    def cancel_split_shipment(self, request: OmsSplitRequest) -> OmsSplitResponse:
        self.runtime.state.split_shipments.discard(request.order_id)
        reference = f"cancelled-split:{request.order_id}"
        return OmsSplitResponse(
            meta=_meta(correlation_id=request.meta.correlation_id, provider_reference=reference),
            order_id=request.order_id,
            split=False,
        )


class SandboxCarrierAdapter:
    def __init__(self, runtime: SharedSandboxRuntime) -> None:
        self.runtime = runtime

    def upgrade_service(self, request: CarrierUpgradeRequest) -> CarrierUpgradeResponse:
        started = perf_counter()
        step = "upgrade_carrier"
        self.runtime.before(step)
        self.runtime.claim_key(
            request.meta.idempotency_key,
            f"carrier:{request.order_id}:{request.to_service}",
        )
        self.runtime.state.carrier_services[request.order_id] = request.to_service
        self.runtime.after(step)
        reference = f"carrier-service:{request.order_id}:{request.to_service}"
        self.runtime.log_call(
            system="carrier", operation=step, reference=reference, started=started
        )
        return CarrierUpgradeResponse(
            meta=_meta(correlation_id=request.meta.correlation_id, provider_reference=reference),
            order_id=request.order_id,
            service=request.to_service,
        )

    def restore_service(self, request: CarrierUpgradeRequest) -> CarrierUpgradeResponse:
        self.runtime.state.carrier_services[request.order_id] = request.from_service
        reference = f"restored-carrier:{request.order_id}:{request.from_service}"
        return CarrierUpgradeResponse(
            meta=_meta(correlation_id=request.meta.correlation_id, provider_reference=reference),
            order_id=request.order_id,
            service=request.from_service,
        )

    def record_delivery(self, request: DeliveryOutcomeRequest) -> DeliveryOutcomeResponse:
        self.runtime.state.delivery_outcomes[request.order_id] = request.delivered_on_time
        reference = f"delivery:{request.order_id}:{request.delivered_on_time}"
        return DeliveryOutcomeResponse(
            meta=_meta(correlation_id=request.meta.correlation_id, provider_reference=reference),
            order_id=request.order_id,
            delivered_on_time=request.delivered_on_time,
        )


class SimulatedOperationsAdapter:
    """Composite sandbox implementing the operations port used by the gateway.

    Preserves the historical method surface used by tests and the action gateway
    while delegating to typed OMS, WMS and carrier sandbox adapters.
    """

    def __init__(self) -> None:
        self.runtime = SharedSandboxRuntime()
        self.wms = SandboxWmsAdapter(self.runtime)
        self.oms = SandboxOmsAdapter(self.runtime)
        self.carrier = SandboxCarrierAdapter(self.runtime)

    @property
    def order_locations(self) -> dict[str, str]:
        return self.runtime.state.order_locations

    @property
    def carrier_services(self) -> dict[str, str]:
        return self.runtime.state.carrier_services

    @property
    def split_shipments(self) -> set[str]:
        return self.runtime.state.split_shipments

    @property
    def alternative_reservations(self) -> set[tuple[str, str]]:
        return self.runtime.state.alternative_reservations

    @property
    def delivery_outcomes(self) -> dict[str, bool]:
        return self.runtime.state.delivery_outcomes

    @property
    def applied_idempotency_keys(self) -> dict[str, str]:
        return self.runtime.state.applied_idempotency_keys

    @property
    def failure_modes(self) -> dict[str, str]:
        return self.runtime.state.failure_modes

    def seed_order(self, order: OrderContext) -> None:
        self.runtime.seed_order(order)

    def inject_failure(self, step_name: str, *, when: str = "before") -> None:
        self.runtime.inject_failure(step_name, when=when)

    def clear_failures(self) -> None:
        self.runtime.clear_failures()

    def record_delivery_outcome(self, order_id: str, *, delivered_on_time: bool) -> None:
        self.carrier.record_delivery(
            DeliveryOutcomeRequest(
                meta=self.runtime.request_meta(
                    f"delivery:{order_id}",
                    tenant_id="local-default",
                    actor_id=None,
                ),
                order_id=order_id,
                delivered_on_time=delivered_on_time,
            )
        )

    def reserve_alternative(self, *, order: OrderContext, idempotency_key: str) -> str:
        if order.alternative_location_id is None:
            raise ActionExecutionError("alternative location is not available")
        response = self.wms.reserve_inventory(
            WmsReserveRequest(
                meta=self.runtime.request_meta(
                    idempotency_key,
                    tenant_id=order.tenant_id,
                    actor_id=None,
                ),
                order_id=order.order_id,
                sku=order.sku,
                quantity=order.quantity,
                location_id=order.alternative_location_id,
            )
        )
        return response.meta.provider_reference

    def release_alternative(self, *, order: OrderContext) -> str:
        response = self.wms.release_inventory(
            WmsReleaseRequest(
                meta=self.runtime.request_meta(
                    f"release:{order.order_id}",
                    tenant_id=order.tenant_id,
                    actor_id=None,
                ),
                order_id=order.order_id,
                location_id=order.alternative_location_id,
            )
        )
        return response.meta.provider_reference

    def change_location(self, *, order: OrderContext, idempotency_key: str) -> str:
        if order.alternative_location_id is None:
            raise ActionExecutionError("alternative location is not available")
        response = self.oms.change_fulfilment_location(
            OmsChangeLocationRequest(
                meta=self.runtime.request_meta(
                    idempotency_key,
                    tenant_id=order.tenant_id,
                    actor_id=None,
                ),
                order_id=order.order_id,
                from_location=order.current_fulfilment_location,
                to_location=order.alternative_location_id,
            )
        )
        return response.meta.provider_reference

    def restore_location(self, *, order: OrderContext) -> str:
        response = self.oms.restore_fulfilment_location(
            OmsChangeLocationRequest(
                meta=self.runtime.request_meta(
                    f"restore-location:{order.order_id}",
                    tenant_id=order.tenant_id,
                    actor_id=None,
                ),
                order_id=order.order_id,
                from_location=order.current_fulfilment_location,
                to_location=order.alternative_location_id or order.current_fulfilment_location,
            )
        )
        return response.meta.provider_reference

    def upgrade_carrier(self, *, order: OrderContext, idempotency_key: str) -> str:
        response = self.carrier.upgrade_service(
            CarrierUpgradeRequest(
                meta=self.runtime.request_meta(
                    idempotency_key,
                    tenant_id=order.tenant_id,
                    actor_id=None,
                ),
                order_id=order.order_id,
                from_service=order.current_carrier_service,
                to_service=order.upgraded_carrier_service,
            )
        )
        return response.meta.provider_reference

    def restore_carrier(self, *, order: OrderContext) -> str:
        response = self.carrier.restore_service(
            CarrierUpgradeRequest(
                meta=self.runtime.request_meta(
                    f"restore-carrier:{order.order_id}",
                    tenant_id=order.tenant_id,
                    actor_id=None,
                ),
                order_id=order.order_id,
                from_service=order.current_carrier_service,
                to_service=order.upgraded_carrier_service,
            )
        )
        return response.meta.provider_reference

    def create_split(self, *, order: OrderContext, idempotency_key: str) -> str:
        if not order.split_shipment_possible:
            raise ActionExecutionError("split shipment is not feasible")
        response = self.oms.create_split_shipment(
            OmsSplitRequest(
                meta=self.runtime.request_meta(
                    idempotency_key,
                    tenant_id=order.tenant_id,
                    actor_id=None,
                ),
                order_id=order.order_id,
                quantity=order.quantity,
            )
        )
        return response.meta.provider_reference

    def cancel_split(self, *, order: OrderContext) -> str:
        response = self.oms.cancel_split_shipment(
            OmsSplitRequest(
                meta=self.runtime.request_meta(
                    f"cancel-split:{order.order_id}",
                    tenant_id=order.tenant_id,
                    actor_id=None,
                ),
                order_id=order.order_id,
                quantity=order.quantity,
            )
        )
        return response.meta.provider_reference

    def action_postcondition_holds(self, *, order: OrderContext, action: RecoveryAction) -> bool:
        if action is RecoveryAction.REROUTE:
            return (
                order.alternative_location_id is not None
                and self.order_locations.get(order.order_id) == order.alternative_location_id
            )
        if action is RecoveryAction.CARRIER_UPGRADE:
            return self.carrier_services.get(order.order_id) == order.upgraded_carrier_service
        if action is RecoveryAction.SPLIT_SHIPMENT:
            return order.order_id in self.split_shipments
        return action is RecoveryAction.TAKE_NO_ACTION

    def hydrate_from_durable_action(
        self, *, order: OrderContext, execution: ActionExecution
    ) -> None:
        """Rebuild sandbox postconditions from durable action evidence after restart."""

        self.seed_order(order)
        if execution.status not in {ActionStatus.SUCCEEDED, ActionStatus.VERIFIED}:
            return
        action = execution.command.action
        if action is RecoveryAction.REROUTE and order.alternative_location_id is not None:
            self.order_locations[order.order_id] = order.alternative_location_id
            self.alternative_reservations.add((order.order_id, order.alternative_location_id))
        elif action is RecoveryAction.CARRIER_UPGRADE:
            self.carrier_services[order.order_id] = order.upgraded_carrier_service
        elif action is RecoveryAction.SPLIT_SHIPMENT:
            self.split_shipments.add(order.order_id)

    def _claim_key(self, key: str, operation: str) -> None:
        self.runtime.claim_key(key, operation)

    def _before(self, step: str) -> None:
        self.runtime.before(step)

    def _after(self, step: str) -> None:
        self.runtime.after(step)
