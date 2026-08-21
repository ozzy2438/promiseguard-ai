from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from promiseguard.approval import ApprovalError
from promiseguard.models import (
    ActionStatus,
    ApprovalDecisionInput,
    ApprovalStatus,
    DeliveryObservation,
    EvaluationRequest,
    OperatingMode,
    RecoveryAction,
    SourceReference,
    UserRole,
    VerificationStatus,
)
from promiseguard.services import ServiceContainer


def _approval_request(request: EvaluationRequest) -> EvaluationRequest:
    return request.model_copy(update={"mode": OperatingMode.APPROVAL})


def _observation(order_id: str, observed_at: datetime) -> DeliveryObservation:
    return DeliveryObservation(
        order_id=order_id,
        delivered_on_time=True,
        observed_at=observed_at,
        source_reference=SourceReference(
            system="carrier",
            record_id=f"delivered:{order_id}",
            observed_at=observed_at,
        ),
    )


def test_approval_execution_and_independent_outcome_verification(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
    evaluation_time: datetime,
) -> None:
    trace = services.evaluation.evaluate(_approval_request(at_risk_request))
    submitted = services.workflow.submit(
        trace.decision_id,
        actor_id="analyst-1",
        now=evaluation_time,
    )

    assert submitted.approval is not None
    assert submitted.approval.status is ApprovalStatus.PENDING
    approved = services.workflow.approve_and_execute(
        submitted.approval.approval_id,
        ApprovalDecisionInput(
            actor_id="manager-1",
            actor_role=UserRole.OPERATIONS_MANAGER,
            reason="Validated inventory and recovery economics",
        ),
        now=evaluation_time + timedelta(minutes=2),
    )

    assert approved.execution is not None
    assert approved.execution.status is ActionStatus.SUCCEEDED
    assert approved.execution.command.action is RecoveryAction.REROUTE
    assert services.adapter.order_locations[at_risk_request.order.order_id] == "FC-SYD"

    verified = services.workflow.verify(
        trace.decision_id,
        observation=_observation(
            at_risk_request.order.order_id,
            evaluation_time + timedelta(days=1),
        ),
        now=evaluation_time + timedelta(days=1),
    )

    assert verified.outcome is not None
    assert verified.outcome.status is VerificationStatus.VERIFIED
    assert verified.outcome.on_time_delivery_observed is True
    assert verified.outcome.realised_gross_margin == Decimal("64.00")


def test_auditor_cannot_approve_action(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
    evaluation_time: datetime,
) -> None:
    trace = services.evaluation.evaluate(_approval_request(at_risk_request))
    pending = services.workflow.submit(
        trace.decision_id,
        actor_id="analyst-1",
        now=evaluation_time,
    ).approval
    assert pending is not None

    with pytest.raises(ApprovalError):
        services.workflow.approve_and_execute(
            pending.approval_id,
            ApprovalDecisionInput(
                actor_id="auditor-1",
                actor_role=UserRole.AUDITOR,
                reason="Attempted approval",
            ),
            now=evaluation_time + timedelta(minutes=1),
        )


def test_expired_approval_is_not_executable(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
    evaluation_time: datetime,
) -> None:
    trace = services.evaluation.evaluate(_approval_request(at_risk_request))
    pending = services.workflow.submit(
        trace.decision_id,
        actor_id="analyst-1",
        now=evaluation_time,
    ).approval
    assert pending is not None

    with pytest.raises(ApprovalError, match="expired"):
        services.workflow.approve_and_execute(
            pending.approval_id,
            ApprovalDecisionInput(
                actor_id="manager-1",
                actor_role=UserRole.OPERATIONS_MANAGER,
                reason="Late approval",
            ),
            now=evaluation_time + timedelta(hours=2),
        )

    persisted = services.approvals.get(pending.approval_id)
    assert persisted is not None
    assert persisted.status is ApprovalStatus.EXPIRED


def test_partial_reroute_failure_is_compensated(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
    evaluation_time: datetime,
) -> None:
    trace = services.evaluation.evaluate(_approval_request(at_risk_request))
    pending = services.workflow.submit(
        trace.decision_id,
        actor_id="analyst-1",
        now=evaluation_time,
    ).approval
    assert pending is not None
    services.adapter.inject_failure("change_location", when="before")

    state = services.workflow.approve_and_execute(
        pending.approval_id,
        ApprovalDecisionInput(
            actor_id="manager-1",
            actor_role=UserRole.OPERATIONS_MANAGER,
            reason="Execute failure-injection scenario",
        ),
        now=evaluation_time + timedelta(minutes=1),
    )

    assert state.execution is not None
    assert state.execution.status is ActionStatus.COMPENSATED
    assert services.adapter.order_locations[at_risk_request.order.order_id] == "FC-MEL"
    assert (
        at_risk_request.order.order_id,
        "FC-SYD",
    ) not in services.adapter.alternative_reservations


def test_ambiguous_provider_timeout_is_verified_before_retry(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
    evaluation_time: datetime,
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
        update={"order": carrier_order, "mode": OperatingMode.APPROVAL}
    )
    trace = services.evaluation.evaluate(request)
    assert trace.recommendation.selected_action is RecoveryAction.CARRIER_UPGRADE
    pending = services.workflow.submit(
        trace.decision_id,
        actor_id="analyst-1",
        now=evaluation_time,
    ).approval
    assert pending is not None
    services.adapter.inject_failure("upgrade_carrier", when="after")

    state = services.workflow.approve_and_execute(
        pending.approval_id,
        ApprovalDecisionInput(
            actor_id="manager-1",
            actor_role=UserRole.OPERATIONS_MANAGER,
            reason="Approved carrier upgrade",
        ),
        now=evaluation_time + timedelta(minutes=1),
    )

    assert state.execution is not None
    assert state.execution.status is ActionStatus.SUCCEEDED
    assert state.execution.steps[0].provider_reference == (
        f"verified-after-timeout:{request.order.order_id}"
    )
    assert services.adapter.carrier_services[request.order.order_id] == "EXPRESS"


def test_bounded_mode_requires_earned_autonomy_by_default(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
) -> None:
    request = at_risk_request.model_copy(update={"mode": OperatingMode.BOUNDED_AUTONOMY})
    trace = services.evaluation.evaluate(request)

    assert trace.policy.execution_allowed is False
    assert trace.policy.reasons == ("ACTION_AUTONOMY_NOT_EARNED",)
    state = services.workflow.submit(trace.decision_id, actor_id="promiseguard-service")

    assert state.execution is None
    assert state.approval is not None


def test_repeated_submit_and_execute_are_idempotent(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
    evaluation_time: datetime,
) -> None:
    trace = services.evaluation.evaluate(_approval_request(at_risk_request))
    first = services.workflow.submit(
        trace.decision_id,
        actor_id="analyst-1",
        now=evaluation_time,
    )
    second = services.workflow.submit(
        trace.decision_id,
        actor_id="analyst-1",
        now=evaluation_time + timedelta(minutes=1),
    )
    assert first.approval == second.approval
    assert first.approval is not None

    executed = services.workflow.approve_and_execute(
        first.approval.approval_id,
        ApprovalDecisionInput(
            actor_id="manager-1",
            actor_role=UserRole.OPERATIONS_MANAGER,
            reason="Approved once",
        ),
        now=evaluation_time + timedelta(minutes=2),
    )
    replay = services.actions.execute(
        executed.execution.command,
        at_risk_request.order,
        now=evaluation_time + timedelta(minutes=3),
    )
    assert replay == executed.execution


def test_operations_analyst_can_approve_within_delegated_cost_limit(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
    evaluation_time: datetime,
) -> None:
    trace = services.evaluation.evaluate(_approval_request(at_risk_request))
    pending = services.workflow.submit(
        trace.decision_id,
        actor_id="analyst-requester",
        now=evaluation_time,
    ).approval
    assert pending is not None

    state = services.workflow.approve_and_execute(
        pending.approval_id,
        ApprovalDecisionInput(
            actor_id="analyst-approver",
            actor_role=UserRole.OPERATIONS_ANALYST,
            reason="Within delegated low-cost approval limit",
        ),
        now=evaluation_time + timedelta(minutes=1),
    )

    assert state.execution is not None
    assert state.execution.status is ActionStatus.SUCCEEDED


def test_operations_analyst_cannot_approve_above_delegated_cost_limit(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
    evaluation_time: datetime,
) -> None:
    expensive_order = at_risk_request.order.model_copy(
        update={
            "gross_margin": Decimal("300.00"),
            "reroute_cost": Decimal("25.00"),
            "carrier_upgrade_cost": Decimal("80.00"),
            "reroute_on_time_probability": 0.99,
        }
    )
    request = at_risk_request.model_copy(
        update={
            "event": at_risk_request.event.model_copy(
                update={
                    "event_id": "evt-expensive-approval",
                    "deduplication_key": "oms:evt-expensive-approval:v1",
                }
            ),
            "order": expensive_order,
            "mode": OperatingMode.APPROVAL,
        }
    )
    trace = services.evaluation.evaluate(request)
    assert trace.recommendation.selected_action is RecoveryAction.REROUTE
    pending = services.workflow.submit(
        trace.decision_id,
        actor_id="analyst-requester",
        now=evaluation_time,
    ).approval
    assert pending is not None

    with pytest.raises(ApprovalError, match="delegated cost limit"):
        services.workflow.approve_and_execute(
            pending.approval_id,
            ApprovalDecisionInput(
                actor_id="analyst-approver",
                actor_role=UserRole.OPERATIONS_ANALYST,
                reason="Attempted approval above delegated limit",
            ),
            now=evaluation_time + timedelta(minutes=1),
        )

    persisted = services.approvals.get(pending.approval_id)
    assert persisted is not None
    assert persisted.status is ApprovalStatus.PENDING
