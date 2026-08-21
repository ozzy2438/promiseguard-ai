from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from promiseguard.autonomy import AutonomyControlError
from promiseguard.execution import ActionExecutionError
from promiseguard.models import (
    ActionStatus,
    ApprovalDecisionInput,
    AutonomyLevel,
    AutonomyUpdateInput,
    DeliveryObservation,
    EvaluationRequest,
    KillSwitchUpdateInput,
    OperatingMode,
    OutcomeVerification,
    RecoveryAction,
    SourceReference,
    UserRole,
    VerificationStatus,
)
from promiseguard.services import ServiceContainer


def _verified_outcome(index: int, observed_at: datetime) -> OutcomeVerification:
    return OutcomeVerification(
        outcome_id=f"out-autonomy-{index:03d}",
        decision_id=f"dec-autonomy-{index:03d}",
        action_id=f"act-autonomy-{index:03d}",
        status=VerificationStatus.VERIFIED,
        verified_at=observed_at,
        on_time_delivery_observed=True,
        actual_intervention_cost=Decimal("8.00"),
        realised_gross_margin=Decimal("64.00"),
        estimated_incremental_value=Decimal("40.00"),
        evidence_references=(
            SourceReference(
                system="carrier",
                record_id=f"delivery-{index:03d}",
                observed_at=observed_at,
            ),
        ),
        details={"source": "test-system-of-record"},
    )


def _earn_reroute_autonomy(
    services: ServiceContainer,
    observed_at: datetime,
) -> None:
    for index in range(services.autonomy.promotion_threshold):
        services.autonomy.record_outcome(
            _verified_outcome(index, observed_at + timedelta(seconds=index)),
            RecoveryAction.REROUTE,
        )
    profile = services.autonomy.set_profile(
        RecoveryAction.REROUTE,
        AutonomyUpdateInput(
            level=AutonomyLevel.BOUNDED_AUTONOMY,
            actor_id="manager-1",
            actor_role=UserRole.OPERATIONS_MANAGER,
            reason="Verified evidence threshold satisfied",
        ),
    )
    assert profile.level is AutonomyLevel.BOUNDED_AUTONOMY


def test_autonomy_profile_starts_in_approval_required_state(
    services: ServiceContainer,
) -> None:
    profile = services.autonomy.profile(RecoveryAction.REROUTE)

    assert profile.level is AutonomyLevel.APPROVAL_REQUIRED
    assert profile.verified_successes == 0
    assert profile.consecutive_verified_successes == 0
    assert profile.reason == "Initial approval-required state"
    assert profile.recommended_for_promotion is False


def test_only_manager_can_change_runtime_controls(
    services: ServiceContainer,
) -> None:
    with pytest.raises(AutonomyControlError, match="operations manager"):
        services.autonomy.set_kill_switch(
            KillSwitchUpdateInput(
                active=True,
                actor_id="auditor-1",
                actor_role=UserRole.AUDITOR,
                reason="Unauthorised change attempt",
            )
        )

    with pytest.raises(AutonomyControlError, match="operations manager"):
        services.autonomy.set_profile(
            RecoveryAction.REROUTE,
            AutonomyUpdateInput(
                level=AutonomyLevel.SUSPENDED,
                actor_id="analyst-1",
                actor_role=UserRole.OPERATIONS_ANALYST,
                reason="Unauthorised profile change",
            ),
        )


def test_bounded_autonomy_requires_verified_evidence(
    services: ServiceContainer,
) -> None:
    with pytest.raises(AutonomyControlError, match="consecutive verified evidence"):
        services.autonomy.set_profile(
            RecoveryAction.REROUTE,
            AutonomyUpdateInput(
                level=AutonomyLevel.BOUNDED_AUTONOMY,
                actor_id="manager-1",
                actor_role=UserRole.OPERATIONS_MANAGER,
                reason="Premature promotion attempt",
            ),
        )


def test_verified_evidence_is_idempotent_and_enables_promotion(
    services: ServiceContainer,
    evaluation_time: datetime,
) -> None:
    first = _verified_outcome(1, evaluation_time)
    services.autonomy.record_outcome(first, RecoveryAction.REROUTE)
    services.autonomy.record_outcome(first, RecoveryAction.REROUTE)

    replayed_profile = services.autonomy.profile(RecoveryAction.REROUTE)
    assert replayed_profile.verified_successes == 1
    assert replayed_profile.consecutive_verified_successes == 1

    for index in range(2, services.autonomy.promotion_threshold + 1):
        services.autonomy.record_outcome(
            _verified_outcome(index, evaluation_time + timedelta(seconds=index)),
            RecoveryAction.REROUTE,
        )

    profile = services.autonomy.profile(RecoveryAction.REROUTE)
    assert profile.verified_successes == services.autonomy.promotion_threshold
    assert profile.consecutive_verified_successes == services.autonomy.promotion_threshold
    assert profile.recommended_for_promotion is True

    promoted = services.autonomy.set_profile(
        RecoveryAction.REROUTE,
        AutonomyUpdateInput(
            level=AutonomyLevel.BOUNDED_AUTONOMY,
            actor_id="manager-1",
            actor_role=UserRole.OPERATIONS_MANAGER,
            reason="Evidence threshold reviewed and accepted",
        ),
    )
    assert promoted.level is AutonomyLevel.BOUNDED_AUTONOMY
    assert promoted.recommended_for_promotion is False


def test_earned_bounded_autonomy_executes_without_approval(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
    evaluation_time: datetime,
) -> None:
    _earn_reroute_autonomy(services, evaluation_time)
    request = at_risk_request.model_copy(update={"mode": OperatingMode.BOUNDED_AUTONOMY})
    trace = services.evaluation.evaluate(request)

    assert trace.policy.execution_allowed is True
    state = services.workflow.submit(
        trace.decision_id,
        actor_id="promiseguard-service",
    )

    assert state.approval is None
    assert state.execution is not None
    assert state.execution.status is ActionStatus.SUCCEEDED


def test_kill_switch_blocks_new_bounded_decisions_and_direct_execution(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
    evaluation_time: datetime,
) -> None:
    _earn_reroute_autonomy(services, evaluation_time)
    enabled = services.autonomy.set_kill_switch(
        KillSwitchUpdateInput(
            active=True,
            actor_id="manager-1",
            actor_role=UserRole.OPERATIONS_MANAGER,
            reason="Operational incident containment",
        )
    )
    assert enabled.active is True

    request = at_risk_request.model_copy(update={"mode": OperatingMode.BOUNDED_AUTONOMY})
    trace = services.evaluation.evaluate(request)
    assert trace.policy.reasons == ("GLOBAL_ACTION_KILL_SWITCH_ACTIVE",)

    approval_trace = services.evaluation.evaluate(
        at_risk_request.model_copy(
            update={
                "event": at_risk_request.event.model_copy(
                    update={
                        "event_id": "evt-kill-switch",
                        "deduplication_key": "oms:evt-kill-switch:v1",
                    }
                ),
                "mode": OperatingMode.APPROVAL,
            }
        )
    )
    pending = services.workflow.submit(
        approval_trace.decision_id,
        actor_id="analyst-1",
    ).approval
    assert pending is not None
    with pytest.raises(ActionExecutionError, match="kill switch"):
        services.workflow.approve_and_execute(
            pending.approval_id,
            ApprovalDecisionInput(
                actor_id="manager-1",
                actor_role=UserRole.OPERATIONS_MANAGER,
                reason="Approval cannot bypass active kill switch",
            ),
        )


def test_compensated_autonomous_action_is_automatically_suspended(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
    evaluation_time: datetime,
) -> None:
    _earn_reroute_autonomy(services, evaluation_time)
    services.adapter.inject_failure("change_location", when="before")
    trace = services.evaluation.evaluate(
        at_risk_request.model_copy(update={"mode": OperatingMode.BOUNDED_AUTONOMY})
    )

    state = services.workflow.submit(
        trace.decision_id,
        actor_id="promiseguard-service",
    )

    assert state.execution is not None
    assert state.execution.status is ActionStatus.COMPENSATED
    profile = services.autonomy.profile(RecoveryAction.REROUTE)
    assert profile.level is AutonomyLevel.SUSPENDED
    assert profile.failure_count == 1
    assert profile.compensation_count == 1
    assert profile.consecutive_verified_successes == 0
    assert profile.reason == "Automatic safety downgrade after EXECUTION_FAILURE"
    assert services.autonomy.execution_permitted(RecoveryAction.REROUTE) is False


def test_manual_review_outcome_does_not_count_as_failure(
    services: ServiceContainer,
    evaluation_time: datetime,
) -> None:
    outcome = _verified_outcome(99, evaluation_time).model_copy(
        update={"status": VerificationStatus.MANUAL_REVIEW_REQUIRED}
    )
    profile = services.autonomy.record_outcome(outcome, RecoveryAction.REROUTE)

    assert profile.verified_successes == 0
    assert profile.failure_count == 0


def test_verified_workflow_outcome_adds_autonomy_evidence(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
    evaluation_time: datetime,
) -> None:
    trace = services.evaluation.evaluate(
        at_risk_request.model_copy(update={"mode": OperatingMode.APPROVAL})
    )
    pending = services.workflow.submit(
        trace.decision_id,
        actor_id="analyst-1",
        now=evaluation_time,
    ).approval
    assert pending is not None
    executed = services.workflow.approve_and_execute(
        pending.approval_id,
        ApprovalDecisionInput(
            actor_id="manager-1",
            actor_role=UserRole.OPERATIONS_MANAGER,
            reason="Verified inventory and margin economics",
        ),
        now=evaluation_time + timedelta(minutes=1),
    )
    assert executed.execution is not None

    services.workflow.verify(
        trace.decision_id,
        observation=DeliveryObservation(
            order_id=at_risk_request.order.order_id,
            delivered_on_time=True,
            observed_at=evaluation_time + timedelta(days=1),
            source_reference=SourceReference(
                system="carrier",
                record_id="delivery-order-001",
                observed_at=evaluation_time + timedelta(days=1),
            ),
        ),
        now=evaluation_time + timedelta(days=1),
    )

    assert services.autonomy.profile(RecoveryAction.REROUTE).verified_successes == 1


def test_control_version_changes_immutable_decision_identity(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
) -> None:
    request = at_risk_request.model_copy(update={"mode": OperatingMode.BOUNDED_AUTONOMY})
    before = services.evaluation.evaluate(request)

    services.autonomy.set_kill_switch(
        KillSwitchUpdateInput(
            active=True,
            actor_id="manager-1",
            actor_role=UserRole.OPERATIONS_MANAGER,
            reason="Versioned safety-control test",
        )
    )
    after = services.evaluation.evaluate(request)

    assert before.decision_id != after.decision_id
    assert before.policy.control_version != after.policy.control_version
    assert after.policy.reasons == ("GLOBAL_ACTION_KILL_SWITCH_ACTIVE",)
    assert services.ledger.count() == 2
