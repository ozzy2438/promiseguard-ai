"""Human-approval workflow with expiry, role checks and durable records."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256

from promiseguard.database import Database
from promiseguard.models import (
    ApprovalDecisionInput,
    ApprovalRecord,
    ApprovalStatus,
    DecisionTrace,
    RecoveryAction,
    UserRole,
)
from promiseguard.persistence import ApprovalRepository, RecordNotFoundError


class ApprovalError(RuntimeError):
    """Raised when approval state or authority is invalid."""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ApprovalService:
    """Create, approve and reject durable action approvals."""

    def __init__(self, database: Database, *, ttl_minutes: int = 60) -> None:
        self.database = database
        self.ttl = timedelta(minutes=ttl_minutes)
        self.repository = ApprovalRepository()

    def request(
        self,
        decision: DecisionTrace,
        *,
        requested_by: str,
        now: datetime | None = None,
    ) -> ApprovalRecord:
        if decision.recommendation.selected_action in {
            RecoveryAction.TAKE_NO_ACTION,
            RecoveryAction.HUMAN_ESCALATION,
        }:
            raise ApprovalError("selected decision does not contain an executable action")
        requested_at = _utc(now or datetime.now(UTC))
        identity = "|".join(
            (
                decision.decision_id,
                decision.recommendation.selected_action.value,
                decision.policy.policy_version,
            )
        )
        approval_id = f"apr_{sha256(identity.encode()).hexdigest()[:24]}"
        record = ApprovalRecord(
            approval_id=approval_id,
            decision_id=decision.decision_id,
            requested_action=decision.recommendation.selected_action,
            status=ApprovalStatus.PENDING,
            requested_by=requested_by,
            requested_at=requested_at,
            expires_at=requested_at + self.ttl,
        )
        with self.database.session() as session:
            existing = self.repository.get(session, approval_id)
            if existing is not None:
                return existing
            return self.repository.create(session, record)

    def approve(
        self,
        approval_id: str,
        decision_input: ApprovalDecisionInput,
        *,
        now: datetime | None = None,
    ) -> ApprovalRecord:
        return self._decide(
            approval_id,
            decision_input,
            target_status=ApprovalStatus.APPROVED,
            now=now,
        )

    def reject(
        self,
        approval_id: str,
        decision_input: ApprovalDecisionInput,
        *,
        now: datetime | None = None,
    ) -> ApprovalRecord:
        return self._decide(
            approval_id,
            decision_input,
            target_status=ApprovalStatus.REJECTED,
            now=now,
        )

    def get(self, approval_id: str) -> ApprovalRecord | None:
        with self.database.session() as session:
            return self.repository.get(session, approval_id)

    def list_pending(self) -> tuple[ApprovalRecord, ...]:
        with self.database.session() as session:
            return self.repository.list_pending(session)

    def _decide(
        self,
        approval_id: str,
        decision_input: ApprovalDecisionInput,
        *,
        target_status: ApprovalStatus,
        now: datetime | None,
    ) -> ApprovalRecord:
        if decision_input.actor_role in {
            UserRole.AUDITOR,
            UserRole.SERVICE_IDENTITY,
        }:
            raise ApprovalError("actor role is not authorised to decide approvals")
        decided_at = _utc(now or datetime.now(UTC))
        expired = False
        result: ApprovalRecord | None = None
        with self.database.session() as session:
            record = self.repository.get(session, approval_id)
            if record is None:
                raise RecordNotFoundError(f"approval {approval_id!r} not found")
            if record.status is not ApprovalStatus.PENDING:
                raise ApprovalError("approval is no longer pending")
            if decided_at > _utc(record.expires_at):
                result = self.repository.update(
                    session,
                    record.model_copy(update={"status": ApprovalStatus.EXPIRED}),
                )
                expired = True
            else:
                updated = record.model_copy(
                    update={
                        "status": target_status,
                        "decided_by": decision_input.actor_id,
                        "decided_by_role": decision_input.actor_role,
                        "decision_reason": decision_input.reason,
                        "decided_at": decided_at,
                    }
                )
                result = self.repository.update(session, updated)
        if expired:
            raise ApprovalError("approval has expired")
        assert result is not None
        return result
