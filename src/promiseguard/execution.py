"""Governed, idempotent and compensatable action execution."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from promiseguard.adapters.errors import (
    ActionExecutionError,
    AdapterError,
    AdapterRateLimited,
    AmbiguousProviderTimeout,
    MalformedAdapterResponse,
)
from promiseguard.adapters.sandbox import SimulatedOperationsAdapter
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

__all__ = [
    "ActionExecutionError",
    "ActionGateway",
    "AmbiguousProviderTimeout",
    "SimulatedOperationsAdapter",
]


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
            except (AmbiguousProviderTimeout, MalformedAdapterResponse):
                if not self.adapter.action_postcondition_holds(
                    order=order, action=RecoveryAction.REROUTE
                ):
                    raise
                reference = f"verified-after-timeout:{order.order_id}"
            steps.append(self._success_step(2, "change_location", now, reference))
        except AdapterRateLimited:
            raise
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
        except (AmbiguousProviderTimeout, MalformedAdapterResponse):
            if not self.adapter.action_postcondition_holds(
                order=order, action=RecoveryAction.CARRIER_UPGRADE
            ):
                raise
            reference = f"verified-after-timeout:{order.order_id}"
        except AdapterError as exc:
            if self.adapter.action_postcondition_holds(
                order=order, action=RecoveryAction.CARRIER_UPGRADE
            ):
                restore_ref = self.adapter.restore_carrier(order=order)
                step = ActionStepResult(
                    sequence=1,
                    step_name="compensate_carrier_upgrade",
                    status=StepStatus.COMPENSATED,
                    attempted_at=now,
                    completed_at=datetime.now(UTC),
                    provider_reference=restore_ref,
                    error_code=type(exc).__name__,
                )
                return execution.model_copy(
                    update={
                        "status": ActionStatus.COMPENSATED,
                        "steps": (step,),
                        "completed_at": datetime.now(UTC),
                        "error_code": type(exc).__name__,
                    }
                )
            raise
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
        except (AmbiguousProviderTimeout, MalformedAdapterResponse):
            if not self.adapter.action_postcondition_holds(
                order=order, action=RecoveryAction.SPLIT_SHIPMENT
            ):
                raise
            reference = f"verified-after-timeout:{order.order_id}"
        except AdapterError as exc:
            if self.adapter.action_postcondition_holds(
                order=order, action=RecoveryAction.SPLIT_SHIPMENT
            ):
                cancel_ref = self.adapter.cancel_split(order=order)
                step = ActionStepResult(
                    sequence=1,
                    step_name="compensate_split",
                    status=StepStatus.COMPENSATED,
                    attempted_at=now,
                    completed_at=datetime.now(UTC),
                    provider_reference=cancel_ref,
                    error_code=type(exc).__name__,
                )
                return execution.model_copy(
                    update={
                        "status": ActionStatus.COMPENSATED,
                        "steps": (step,),
                        "completed_at": datetime.now(UTC),
                        "error_code": type(exc).__name__,
                    }
                )
            raise
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
