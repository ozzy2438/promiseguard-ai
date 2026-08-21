from __future__ import annotations

from decimal import Decimal

import pytest

from promiseguard.adapters import (
    CARRIER_CONTRACT,
    OMS_CONTRACT,
    WMS_CONTRACT,
    AdapterErrorClass,
    MalformedAdapterResponse,
    SimulatedOperationsAdapter,
)
from promiseguard.adapters.contracts import AdapterRequestMeta, WmsReserveRequest
from promiseguard.adapters.errors import AdapterRateLimited
from promiseguard.models import (
    ActionStatus,
    ApprovalDecisionInput,
    EvaluationRequest,
    OperatingMode,
    RecoveryAction,
    UserRole,
)
from promiseguard.services import ServiceContainer


def _approval(request: EvaluationRequest) -> EvaluationRequest:
    return request.model_copy(update={"mode": OperatingMode.APPROVAL})


def _approve(services: ServiceContainer, request: EvaluationRequest, evaluation_time):
    trace = services.evaluation.evaluate(_approval(request))
    pending = services.workflow.submit(
        trace.decision_id,
        actor_id="analyst-1",
        now=evaluation_time,
    ).approval
    assert pending is not None
    return services.workflow.approve_and_execute(
        pending.approval_id,
        ApprovalDecisionInput(
            actor_id="manager-1",
            actor_role=UserRole.OPERATIONS_MANAGER,
            reason="Adapter contract validation",
        ),
        now=evaluation_time,
    )


def test_adapter_contracts_define_safe_execution_semantics() -> None:
    for contract in (WMS_CONTRACT, OMS_CONTRACT, CARRIER_CONTRACT):
        assert contract.contract_version == "v1"
        assert contract.retry.max_attempts == 1
        assert AdapterErrorClass.AMBIGUOUS in contract.error_classes
        assert "read" in contract.idempotency.verification_after_timeout
        assert contract.compensating_actions
        assert "idempotency_key" in contract.audit_evidence
        assert "correlation_id" in contract.audit_evidence


def test_typed_sandbox_adapters_share_postconditions(
    at_risk_request: EvaluationRequest,
) -> None:
    adapter = SimulatedOperationsAdapter()
    adapter.seed_order(at_risk_request.order)
    reserved = adapter.wms.reserve_inventory(
        WmsReserveRequest(
            meta=AdapterRequestMeta(
                correlation_id="corr_adapter_contract_test",
                idempotency_key="pg-test-reserve-key-0001",
                tenant_id=at_risk_request.order.tenant_id,
            ),
            order_id=at_risk_request.order.order_id,
            sku=at_risk_request.order.sku,
            quantity=at_risk_request.order.quantity,
            location_id="FC-SYD",
        )
    )
    assert reserved.meta.error_class is AdapterErrorClass.SUCCESS
    assert ("order-001", "FC-SYD") in adapter.alternative_reservations


def test_malformed_carrier_response_is_verified_before_retry(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
    evaluation_time,
) -> None:
    carrier_order = at_risk_request.order.model_copy(
        update={
            "alternative_location_available": False,
            "alternative_location_id": None,
            "carrier_upgrade_cost": Decimal("6.00"),
            "carrier_upgrade_on_time_probability": 0.96,
        }
    )
    request = at_risk_request.model_copy(
        update={
            "event": at_risk_request.event.model_copy(
                update={
                    "event_id": "evt-malformed-carrier",
                    "deduplication_key": "oms:evt-malformed-carrier:v1",
                }
            ),
            "order": carrier_order,
            "mode": OperatingMode.APPROVAL,
        }
    )
    services.adapter.inject_failure("upgrade_carrier", when="malformed")
    state = _approve(services, request, evaluation_time)
    assert state.execution is not None
    assert state.execution.status is ActionStatus.SUCCEEDED
    assert "verified-after-timeout" in (state.execution.steps[0].provider_reference or "")


def test_rate_limited_write_does_not_mutate_and_does_not_retry(
    at_risk_request: EvaluationRequest,
) -> None:
    adapter = SimulatedOperationsAdapter()
    adapter.seed_order(at_risk_request.order)
    adapter.inject_failure("upgrade_carrier", when="rate_limited")
    with pytest.raises(AdapterRateLimited):
        adapter.upgrade_carrier(order=at_risk_request.order, idempotency_key="pg-rate-limit-key-1")
    assert adapter.carrier_services[at_risk_request.order.order_id] == "STANDARD"


def test_hard_failure_after_carrier_write_is_compensated(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
    evaluation_time,
) -> None:
    carrier_order = at_risk_request.order.model_copy(
        update={
            "alternative_location_available": False,
            "alternative_location_id": None,
            "carrier_upgrade_cost": Decimal("6.00"),
            "carrier_upgrade_on_time_probability": 0.96,
        }
    )
    request = at_risk_request.model_copy(
        update={
            "event": at_risk_request.event.model_copy(
                update={
                    "event_id": "evt-hard-after-carrier",
                    "deduplication_key": "oms:evt-hard-after-carrier:v1",
                }
            ),
            "order": carrier_order,
            "mode": OperatingMode.APPROVAL,
        }
    )
    services.adapter.inject_failure("upgrade_carrier", when="hard_after")
    state = _approve(services, request, evaluation_time)
    assert state.execution is not None
    assert state.execution.status is ActionStatus.COMPENSATED
    assert services.adapter.carrier_services[request.order.order_id] == "STANDARD"


def test_hard_failure_after_split_write_is_compensated(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
    evaluation_time,
) -> None:
    split_order = at_risk_request.order.model_copy(
        update={
            "alternative_location_available": False,
            "alternative_location_id": None,
            "carrier_upgrade_on_time_probability": 0.40,
            "carrier_upgrade_cost": Decimal("40.00"),
            "split_shipment_possible": True,
            "split_shipment_on_time_probability": 0.97,
            "split_shipment_cost": Decimal("4.00"),
        }
    )
    request = at_risk_request.model_copy(
        update={
            "event": at_risk_request.event.model_copy(
                update={
                    "event_id": "evt-hard-after-split",
                    "deduplication_key": "oms:evt-hard-after-split:v1",
                }
            ),
            "order": split_order,
            "mode": OperatingMode.APPROVAL,
        }
    )
    trace = services.evaluation.evaluate(request)
    assert trace.recommendation.selected_action is RecoveryAction.SPLIT_SHIPMENT
    services.adapter.inject_failure("create_split", when="hard_after")
    pending = services.workflow.submit(
        trace.decision_id, actor_id="analyst-1", now=evaluation_time
    ).approval
    assert pending is not None
    state = services.workflow.approve_and_execute(
        pending.approval_id,
        ApprovalDecisionInput(
            actor_id="manager-1",
            actor_role=UserRole.OPERATIONS_MANAGER,
            reason="Split compensation evidence",
        ),
        now=evaluation_time,
    )
    assert state.execution is not None
    assert state.execution.status is ActionStatus.COMPENSATED
    assert request.order.order_id not in services.adapter.split_shipments


def test_malformed_response_without_postcondition_is_ambiguous(
    at_risk_request: EvaluationRequest,
) -> None:
    adapter = SimulatedOperationsAdapter()
    adapter.seed_order(at_risk_request.order)
    adapter.inject_failure("reserve_alternative", when="malformed")
    # Mutation happens before the malformed signal, so callers must verify.
    with pytest.raises(MalformedAdapterResponse):
        adapter.reserve_alternative(
            order=at_risk_request.order,
            idempotency_key="pg-malformed-reserve-key",
        )
    assert ("order-001", "FC-SYD") in adapter.alternative_reservations
