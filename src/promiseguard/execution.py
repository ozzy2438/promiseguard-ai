"""Governed, idempotent and compensatable action execution."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from promiseguard.autonomy import AutonomyController
from promiseguard.database import Database
from promiseguard.models import (
    ActionCommand,
    ActionExecution,
    ActionStatus,
    ActionStepResult,
    OrderContext,
    RecoveryAction,
    StepStatus,
)
from promiseguard.persistence import ActionRepository, PersistenceConflictError


class ActionExecutionError(RuntimeError):
    """Raised when a governed action cannot be completed safely."""


class AmbiguousProviderTimeout(TimeoutError):
    """Provider timed out after the external state may already have changed."""


class SimulatedOperationsAdapter:
    """Deterministic local systems-of-record adapter with failure injection."""

    def __init__(self) -> None:
        self.order_locations: dict[str, str] = {}
        self.carrier_services: dict[str, str] = {}
        self.split_shipments: set[str] = set()
        self.alternative_reservations: set[tuple[str, str]] = set()
        self.delivery_outcomes: dict[str, bool] = {}
        self.applied_idempotency_keys: dict[str, str] = {}
        self.failure_modes: dict[str, str] = {}

    def seed_order(self, order: OrderContext) -> None:
        self.order_locations.setdefault(order.order_id, order.current_fulfilment_location)
        self.carrier_services.setdefault(order.order_id, order.current_carrier_service)

    def inject_failure(self, step_name: str, *, when: str = "before") -> None:
        if when not in {"before", "after"}:
            raise ValueError("failure timing must be 'before' or 'after'")
        self.failure_modes[step_name] = when

    def clear_failures(self) -> None:
        self.failure_modes.clear()

    def record_delivery_outcome(self, order_id: str, *, delivered_on_time: bool) -> None:
        self.delivery_outcomes[order_id] = delivered_on_time

    def reserve_alternative(self, *, order: OrderContext, idempotency_key: str) -> str:
        step = "reserve_alternative"
        self._before(step)
        if order.alternative_location_id is None:
            raise ActionExecutionError("alternative location is not available")
        self._claim_key(
            idempotency_key,
            f"reserve:{order.order_id}:{order.alternative_location_id}",
        )
        self.alternative_reservations.add((order.order_id, order.alternative_location_id))
        self._after(step)
        return f"reservation:{order.order_id}:{order.alternative_location_id}"

    def release_alternative(self, *, order: OrderContext) -> str:
        if order.alternative_location_id is not None:
            self.alternative_reservations.discard((order.order_id, order.alternative_location_id))
        return f"released:{order.order_id}"

    def change_location(self, *, order: OrderContext, idempotency_key: str) -> str:
        step = "change_location"
        self._before(step)
        if order.alternative_location_id is None:
            raise ActionExecutionError("alternative location is not available")
        self._claim_key(
            idempotency_key,
            f"reroute:{order.order_id}:{order.alternative_location_id}",
        )
        self.order_locations[order.order_id] = order.alternative_location_id
        self._after(step)
        return f"order-location:{order.order_id}:{order.alternative_location_id}"

    def restore_location(self, *, order: OrderContext) -> str:
        self.order_locations[order.order_id] = order.current_fulfilment_location
        return f"restored-location:{order.order_id}:{order.current_fulfilment_location}"

    def upgrade_carrier(self, *, order: OrderContext, idempotency_key: str) -> str:
        step = "upgrade_carrier"
        self._before(step)
        self._claim_key(
            idempotency_key,
            f"carrier:{order.order_id}:{order.upgraded_carrier_service}",
        )
        self.carrier_services[order.order_id] = order.upgraded_carrier_service
        self._after(step)
        return f"carrier-service:{order.order_id}:{order.upgraded_carrier_service}"

    def restore_carrier(self, *, order: OrderContext) -> str:
        self.carrier_services[order.order_id] = order.current_carrier_service
        return f"restored-carrier:{order.order_id}:{order.current_carrier_service}"

    def create_split(self, *, order: OrderContext, idempotency_key: str) -> str:
        step = "create_split"
        self._before(step)
        if not order.split_shipment_possible:
            raise ActionExecutionError("split shipment is not feasible")
        self._claim_key(idempotency_key, f"split:{order.order_id}")
        self.split_shipments.add(order.order_id)
        self._after(step)
        return f"split-shipment:{order.order_id}"

    def cancel_split(self, *, order: OrderContext) -> str:
        self.split_shipments.discard(order.order_id)
        return f"cancelled-split:{order.order_id}"

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

    def _claim_key(self, key: str, operation: str) -> None:
        existing = self.applied_idempotency_keys.get(key)
        if existing is not None and existing != operation:
            raise PersistenceConflictError(
                "provider idempotency key was reused for a different operation"
            )
        self.applied_idempotency_keys[key] = operation

    def _before(self, step: str) -> None:
        if self.failure_modes.get(step) == "before":
            raise ActionExecutionError(f"injected failure before {step}")

    def _after(self, step: str) -> None:
        if self.failure_modes.get(step) == "after":
            raise AmbiguousProviderTimeout(f"injected timeout after {step}")


class ActionGateway:
    """Execute approved commands and preserve idempotent recovery evidence."""

    def __init__(
        self,
        database: Database,
        adapter: SimulatedOperationsAdapter,
        autonomy: AutonomyController | None = None,
    ) -> None:
        self.database = database
        self.adapter = adapter
        self.autonomy = autonomy
        self.repository = ActionRepository()

    def execute(
        self,
        command: ActionCommand,
        order: OrderContext,
        *,
        now: datetime | None = None,
    ) -> ActionExecution:
        started_at = now or datetime.now(UTC)
        if self.autonomy is not None and self.autonomy.kill_switch().active:
            raise ActionExecutionError("global action kill switch is active")
        with self.database.session() as session:
            existing = self.repository.get_by_decision(session, command.decision_id)
            if existing is not None:
                if existing.command.idempotency_key != command.idempotency_key:
                    raise PersistenceConflictError(
                        "decision already has an action with a different idempotency key"
                    )
                return existing

            action_id = f"act_{sha256(command.idempotency_key.encode()).hexdigest()[:24]}"
            executing = ActionExecution(
                action_id=action_id,
                command=command,
                status=ActionStatus.EXECUTING,
                steps=(),
                started_at=started_at,
            )
            self.repository.record(session, executing)

        self.adapter.seed_order(order)
        try:
            completed = self._execute_steps(executing, order, now=started_at)
        except Exception as exc:
            failed = ActionExecution(
                action_id=executing.action_id,
                command=command,
                status=ActionStatus.FAILED,
                steps=(),
                started_at=started_at,
                completed_at=datetime.now(UTC),
                error_code=type(exc).__name__,
                manual_recovery_reason=str(exc),
            )
            with self.database.session() as session:
                persisted_failure = self.repository.update(session, failed)
            if self.autonomy is not None:
                self.autonomy.record_execution(persisted_failure)
            raise

        with self.database.session() as session:
            persisted = self.repository.update(session, completed)
        if self.autonomy is not None:
            self.autonomy.record_execution(persisted)
        return persisted

    def get(self, action_id: str) -> ActionExecution | None:
        with self.database.session() as session:
            return self.repository.get(session, action_id)

    def get_by_decision(self, decision_id: str) -> ActionExecution | None:
        with self.database.session() as session:
            return self.repository.get_by_decision(session, decision_id)

    def _execute_steps(
        self,
        execution: ActionExecution,
        order: OrderContext,
        *,
        now: datetime,
    ) -> ActionExecution:
        action = execution.command.action
        if action is RecoveryAction.REROUTE:
            return self._reroute(execution, order, now=now)
        if action is RecoveryAction.CARRIER_UPGRADE:
            return self._carrier_upgrade(execution, order, now=now)
        if action is RecoveryAction.SPLIT_SHIPMENT:
            return self._split(execution, order, now=now)
        raise ActionExecutionError(f"action {action.value} is not executable")

    def _reroute(
        self, execution: ActionExecution, order: OrderContext, *, now: datetime
    ) -> ActionExecution:
        steps: list[ActionStepResult] = []
        reserve_key = f"{execution.command.idempotency_key}:reserve"
        change_key = f"{execution.command.idempotency_key}:change-location"
        try:
            reference = self.adapter.reserve_alternative(order=order, idempotency_key=reserve_key)
            steps.append(self._success_step(1, "reserve_alternative", now, reference))
            try:
                reference = self.adapter.change_location(order=order, idempotency_key=change_key)
            except AmbiguousProviderTimeout:
                if not self.adapter.action_postcondition_holds(
                    order=order, action=RecoveryAction.REROUTE
                ):
                    raise
                reference = f"verified-after-timeout:{order.order_id}"
            steps.append(self._success_step(2, "change_location", now, reference))
        except Exception as exc:
            if steps:
                restore_ref = self.adapter.restore_location(order=order)
                release_ref = self.adapter.release_alternative(order=order)
                steps.append(
                    ActionStepResult(
                        sequence=len(steps) + 1,
                        step_name="compensate_reroute",
                        status=StepStatus.COMPENSATED,
                        attempted_at=now,
                        completed_at=datetime.now(UTC),
                        provider_reference=restore_ref,
                        details={"release_reference": release_ref},
                        error_code=type(exc).__name__,
                    )
                )
                return execution.model_copy(
                    update={
                        "status": ActionStatus.COMPENSATED,
                        "steps": tuple(steps),
                        "completed_at": datetime.now(UTC),
                        "error_code": type(exc).__name__,
                    }
                )
            raise
        return execution.model_copy(
            update={
                "status": ActionStatus.SUCCEEDED,
                "steps": tuple(steps),
                "completed_at": datetime.now(UTC),
            }
        )

    def _carrier_upgrade(
        self, execution: ActionExecution, order: OrderContext, *, now: datetime
    ) -> ActionExecution:
        try:
            reference = self.adapter.upgrade_carrier(
                order=order,
                idempotency_key=f"{execution.command.idempotency_key}:carrier",
            )
        except AmbiguousProviderTimeout:
            if not self.adapter.action_postcondition_holds(
                order=order, action=RecoveryAction.CARRIER_UPGRADE
            ):
                raise
            reference = f"verified-after-timeout:{order.order_id}"
        step = self._success_step(1, "upgrade_carrier", now, reference)
        return execution.model_copy(
            update={
                "status": ActionStatus.SUCCEEDED,
                "steps": (step,),
                "completed_at": datetime.now(UTC),
            }
        )

    def _split(
        self, execution: ActionExecution, order: OrderContext, *, now: datetime
    ) -> ActionExecution:
        try:
            reference = self.adapter.create_split(
                order=order,
                idempotency_key=f"{execution.command.idempotency_key}:split",
            )
        except AmbiguousProviderTimeout:
            if not self.adapter.action_postcondition_holds(
                order=order, action=RecoveryAction.SPLIT_SHIPMENT
            ):
                raise
            reference = f"verified-after-timeout:{order.order_id}"
        step = self._success_step(1, "create_split", now, reference)
        return execution.model_copy(
            update={
                "status": ActionStatus.SUCCEEDED,
                "steps": (step,),
                "completed_at": datetime.now(UTC),
            }
        )

    @staticmethod
    def _success_step(
        sequence: int, step_name: str, attempted_at: datetime, reference: str
    ) -> ActionStepResult:
        return ActionStepResult(
            sequence=sequence,
            step_name=step_name,
            status=StepStatus.SUCCEEDED,
            attempted_at=attempted_at,
            completed_at=datetime.now(UTC),
            provider_reference=reference,
        )
