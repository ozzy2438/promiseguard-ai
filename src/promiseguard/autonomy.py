"""Persistent kill switch and evidence-based action autonomy controls."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from promiseguard.database import Database
from promiseguard.db_models import (
    AutonomyEvidenceRow,
    AutonomyProfileRow,
    RuntimeControlRow,
)
from promiseguard.models import (
    ActionExecution,
    ActionStatus,
    AutonomyLevel,
    AutonomyProfile,
    AutonomyUpdateInput,
    KillSwitchState,
    KillSwitchUpdateInput,
    OutcomeVerification,
    RecoveryAction,
    UserRole,
    VerificationStatus,
)
from promiseguard.persistence import ensure_utc


class AutonomyControlError(RuntimeError):
    """Raised when a control change lacks authority or violates policy."""


class AutonomyController:
    """Gate execution and maintain evidence-based action profiles."""

    kill_switch_key = "global_action_kill_switch"
    promotion_threshold = 20

    def __init__(self, database: Database) -> None:
        self.database = database
        self._bootstrap()

    def kill_switch(self) -> KillSwitchState:
        with self.database.session() as session:
            row = session.get(RuntimeControlRow, self.kill_switch_key)
            assert row is not None
            return self._kill_switch_model(row)

    def set_kill_switch(self, update: KillSwitchUpdateInput) -> KillSwitchState:
        self._require_manager(update.actor_role)
        now = datetime.now(UTC)
        with self.database.session() as session:
            row = session.scalar(
                select(RuntimeControlRow)
                .where(RuntimeControlRow.control_key == self.kill_switch_key)
                .with_for_update()
            )
            assert row is not None
            row.enabled = update.active
            row.reason = update.reason
            row.updated_by = update.actor_id
            row.updated_at = now
            row.version += 1
            session.flush()
            return self._kill_switch_model(row)

    def profile(self, action: RecoveryAction) -> AutonomyProfile:
        with self.database.session() as session:
            row = session.get(AutonomyProfileRow, action.value)
            if row is None:
                raise AutonomyControlError(f"action {action.value} has no autonomy profile")
            return self._profile_model(row)

    def profiles(self) -> tuple[AutonomyProfile, ...]:
        with self.database.session() as session:
            rows = session.scalars(
                select(AutonomyProfileRow).order_by(AutonomyProfileRow.action)
            ).all()
            return tuple(self._profile_model(row) for row in rows)

    def set_profile(
        self,
        action: RecoveryAction,
        update: AutonomyUpdateInput,
    ) -> AutonomyProfile:
        self._require_manager(update.actor_role)
        if action in {RecoveryAction.TAKE_NO_ACTION, RecoveryAction.HUMAN_ESCALATION}:
            raise AutonomyControlError("non-executable action has no autonomy profile")
        now = datetime.now(UTC)
        with self.database.session() as session:
            row = session.scalar(
                select(AutonomyProfileRow)
                .where(AutonomyProfileRow.action == action.value)
                .with_for_update()
            )
            if row is None:
                raise AutonomyControlError(f"action {action.value} has no autonomy profile")
            if (
                update.level is AutonomyLevel.BOUNDED_AUTONOMY
                and row.consecutive_verified_successes < self.promotion_threshold
            ):
                raise AutonomyControlError(
                    "bounded autonomy requires sufficient consecutive verified evidence"
                )
            row.level = update.level.value
            row.reason = update.reason
            row.updated_by = update.actor_id
            row.updated_at = now
            row.version += 1
            session.flush()
            return self._profile_model(row)

    def context_version(self, action: RecoveryAction) -> str:
        kill_switch = self.kill_switch()
        if action in {RecoveryAction.TAKE_NO_ACTION, RecoveryAction.HUMAN_ESCALATION}:
            return f"kill-switch:{kill_switch.version}"
        profile = self.profile(action)
        return f"kill-switch:{kill_switch.version}|{action.value}:{profile.version}"

    def execution_permitted(self, action: RecoveryAction) -> bool:
        if self.kill_switch().active:
            return False
        return self.profile(action).level is AutonomyLevel.BOUNDED_AUTONOMY

    def record_execution(self, execution: ActionExecution) -> AutonomyProfile:
        if execution.status not in {
            ActionStatus.COMPENSATED,
            ActionStatus.FAILED,
            ActionStatus.MANUAL_RECOVERY_REQUIRED,
        }:
            return self.profile(execution.command.action)
        return self._record_evidence(
            evidence_id=f"execution:{execution.action_id}",
            action=execution.command.action,
            kind="EXECUTION_FAILURE",
            successful=False,
            compensated=execution.status is ActionStatus.COMPENSATED,
        )

    def record_outcome(
        self, outcome: OutcomeVerification, action: RecoveryAction
    ) -> AutonomyProfile:
        if outcome.status is VerificationStatus.MANUAL_REVIEW_REQUIRED:
            return self.profile(action)
        return self._record_evidence(
            evidence_id=f"outcome:{outcome.outcome_id}",
            action=action,
            kind="VERIFIED_OUTCOME",
            successful=outcome.status is VerificationStatus.VERIFIED,
            compensated=False,
        )

    def _record_evidence(
        self,
        *,
        evidence_id: str,
        action: RecoveryAction,
        kind: str,
        successful: bool,
        compensated: bool,
    ) -> AutonomyProfile:
        now = datetime.now(UTC)
        with self.database.session() as session:
            existing = session.get(AutonomyEvidenceRow, evidence_id)
            row = session.scalar(
                select(AutonomyProfileRow)
                .where(AutonomyProfileRow.action == action.value)
                .with_for_update()
            )
            if row is None:
                raise AutonomyControlError(f"action {action.value} has no autonomy profile")
            if existing is not None:
                return self._profile_model(row)
            session.add(
                AutonomyEvidenceRow(
                    evidence_id=evidence_id,
                    action=action.value,
                    evidence_kind=kind,
                    successful=successful,
                    compensated=compensated,
                    created_at=now,
                )
            )
            if successful:
                row.verified_successes += 1
                row.consecutive_verified_successes += 1
            else:
                row.failure_count += 1
                row.consecutive_verified_successes = 0
            if compensated:
                row.compensation_count += 1
            if not successful and row.level == AutonomyLevel.BOUNDED_AUTONOMY.value:
                row.level = AutonomyLevel.SUSPENDED.value
                row.reason = f"Automatic safety downgrade after {kind}"
                row.updated_by = "automatic-safety-downgrade"
            row.last_evidence_at = now
            row.updated_at = now
            row.version += 1
            session.flush()
            return self._profile_model(row)

    def _bootstrap(self) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            if session.get(RuntimeControlRow, self.kill_switch_key) is None:
                session.add(
                    RuntimeControlRow(
                        control_key=self.kill_switch_key,
                        enabled=False,
                        reason="Initial safe state",
                        updated_by="system-bootstrap",
                        updated_at=now,
                        version=1,
                    )
                )
            for action in (
                RecoveryAction.REROUTE,
                RecoveryAction.CARRIER_UPGRADE,
                RecoveryAction.SPLIT_SHIPMENT,
            ):
                if session.get(AutonomyProfileRow, action.value) is None:
                    session.add(
                        AutonomyProfileRow(
                            action=action.value,
                            level=AutonomyLevel.APPROVAL_REQUIRED.value,
                            verified_successes=0,
                            consecutive_verified_successes=0,
                            compensation_count=0,
                            failure_count=0,
                            reason="Initial approval-required state",
                            last_evidence_at=None,
                            updated_by="system-bootstrap",
                            updated_at=now,
                            version=1,
                        )
                    )

    @classmethod
    def _profile_model(cls, row: AutonomyProfileRow) -> AutonomyProfile:
        return AutonomyProfile.model_validate(
            {
                "action": row.action,
                "level": row.level,
                "verified_successes": row.verified_successes,
                "consecutive_verified_successes": row.consecutive_verified_successes,
                "compensation_count": row.compensation_count,
                "failure_count": row.failure_count,
                "recommended_for_promotion": (
                    row.consecutive_verified_successes >= cls.promotion_threshold
                    and row.level != AutonomyLevel.BOUNDED_AUTONOMY.value
                ),
                "reason": row.reason,
                "last_evidence_at": ensure_utc(row.last_evidence_at),
                "updated_by": row.updated_by,
                "updated_at": ensure_utc(row.updated_at),
                "version": row.version,
            }
        )

    @staticmethod
    def _kill_switch_model(row: RuntimeControlRow) -> KillSwitchState:
        return KillSwitchState.model_validate(
            {
                "active": row.enabled,
                "reason": row.reason,
                "updated_by": row.updated_by,
                "updated_at": ensure_utc(row.updated_at),
                "version": row.version,
            }
        )

    @staticmethod
    def _require_manager(role: UserRole) -> None:
        if role is not UserRole.OPERATIONS_MANAGER:
            raise AutonomyControlError("only an operations manager may change autonomy controls")
