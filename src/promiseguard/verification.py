"""Independent post-action verification and value recording."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from hashlib import sha256

from promiseguard.autonomy import AutonomyController
from promiseguard.database import Database
from promiseguard.execution import SimulatedOperationsAdapter
from promiseguard.models import (
    ActionExecution,
    ActionStatus,
    DecisionTrace,
    DeliveryObservation,
    OrderContext,
    OutcomeVerification,
    VerificationStatus,
)
from promiseguard.persistence import OutcomeRepository

_CENTS = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


class OutcomeVerificationService:
    """Verify external postconditions before recording a realised outcome."""

    def __init__(
        self,
        database: Database,
        adapter: SimulatedOperationsAdapter,
        autonomy: AutonomyController | None = None,
    ) -> None:
        self.database = database
        self.adapter = adapter
        self.autonomy = autonomy
        self.repository = OutcomeRepository()

    def record_delivery_observation(self, observation: DeliveryObservation) -> None:
        self.adapter.record_delivery_outcome(
            observation.order_id,
            delivered_on_time=observation.delivered_on_time,
        )

    def verify(
        self,
        *,
        decision: DecisionTrace,
        execution: ActionExecution,
        order: OrderContext,
        observation: DeliveryObservation | None = None,
        now: datetime | None = None,
    ) -> OutcomeVerification:
        if observation is not None:
            if observation.order_id != order.order_id:
                raise ValueError("delivery observation does not belong to the decision order")
            self.record_delivery_observation(observation)

        verified_at = now or datetime.now(UTC)
        self.adapter.hydrate_from_durable_action(order=order, execution=execution)
        action_postcondition = self.adapter.action_postcondition_holds(
            order=order,
            action=execution.command.action,
        )
        delivered = self.adapter.delivery_outcomes.get(order.order_id)
        if execution.status is ActionStatus.COMPENSATED or not action_postcondition:
            status = VerificationStatus.FAILED
        elif delivered is None:
            status = VerificationStatus.MANUAL_REVIEW_REQUIRED
        else:
            status = VerificationStatus.VERIFIED

        selected = next(
            option
            for option in decision.recommendation.ranked_options
            if option.action is execution.command.action
        )
        actual_cost = execution.command.expected_intervention_cost
        if delivered is True:
            realised_margin = _money(order.gross_margin - actual_cost)
        elif delivered is False:
            realised_margin = _money(-order.cancellation_cost - order.support_cost - actual_cost)
        else:
            realised_margin = Decimal("0.00")

        outcome_id = f"out_{sha256(decision.decision_id.encode()).hexdigest()[:24]}"
        source_references = list(order.source_references)
        if observation is not None:
            source_references.append(observation.source_reference)
        outcome = OutcomeVerification(
            outcome_id=outcome_id,
            decision_id=decision.decision_id,
            action_id=execution.action_id,
            status=status,
            verified_at=verified_at,
            on_time_delivery_observed=delivered,
            actual_intervention_cost=actual_cost,
            realised_gross_margin=realised_margin,
            estimated_incremental_value=(
                decision.recommendation.expected_incremental_value_vs_no_action
            ),
            evidence_references=tuple(source_references),
            details={
                "action_postcondition_holds": action_postcondition,
                "expected_on_time_probability": selected.on_time_probability,
                "execution_status": execution.status.value,
                "verification_source": "simulated_systems_of_record",
            },
        )
        with self.database.session() as session:
            persisted = self.repository.record(session, outcome)
        if self.autonomy is not None:
            self.autonomy.record_outcome(persisted, execution.command.action)
        return persisted

    def get_by_decision(self, decision_id: str) -> OutcomeVerification | None:
        with self.database.session() as session:
            return self.repository.get_by_decision(session, decision_id)
