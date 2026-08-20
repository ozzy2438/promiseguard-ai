"""Persistence repositories with immutable and idempotent semantics."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from promiseguard.db_models import (
    ActionRow,
    ApprovalRow,
    DecisionRow,
    OperationalEventRow,
    OutcomeRow,
)
from promiseguard.models import (
    ActionExecution,
    ApprovalRecord,
    ApprovalStatus,
    DecisionTrace,
    OperationalEvent,
    OutcomeVerification,
)


class PersistenceConflictError(RuntimeError):
    """Raised when an immutable identity is reused with conflicting content."""


class RecordNotFoundError(LookupError):
    """Raised when a required persisted record does not exist."""


def canonical_fingerprint(payload: Any) -> str:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(canonical.encode("utf-8")).hexdigest()


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class EventRepository:
    def ingest(
        self,
        session: Session,
        *,
        event: OperationalEvent,
        payload: dict[str, Any],
    ) -> OperationalEventRow:
        fingerprint = canonical_fingerprint(payload)
        existing = session.scalar(
            select(OperationalEventRow).where(
                OperationalEventRow.source_system == event.source_system,
                OperationalEventRow.event_id == event.event_id,
                OperationalEventRow.event_version == event.event_version,
            )
        )
        if existing is not None:
            if existing.fingerprint != fingerprint:
                raise PersistenceConflictError(
                    "event identity was replayed with conflicting payload"
                )
            return existing

        row = OperationalEventRow(
            source_system=event.source_system,
            event_id=event.event_id,
            event_version=event.event_version,
            event_type=event.event_type,
            event_time=event.event_time,
            ingestion_time=event.ingestion_time,
            schema_version=event.schema_version,
            deduplication_key=event.deduplication_key,
            payload=payload,
            fingerprint=fingerprint,
            created_at=datetime.now(UTC),
        )
        session.add(row)
        session.flush()
        return row

    def get_request_payload(
        self, session: Session, *, event_id: str
    ) -> dict[str, Any] | None:
        row = session.scalar(
            select(OperationalEventRow)
            .where(OperationalEventRow.event_id == event_id)
            .order_by(OperationalEventRow.event_version.desc())
        )
        return None if row is None else dict(row.payload)


class DecisionRepository:
    def record(self, session: Session, trace: DecisionTrace) -> DecisionTrace:
        fingerprint = canonical_fingerprint(trace)
        existing = session.get(DecisionRow, trace.decision_id)
        if existing is not None:
            if existing.fingerprint != fingerprint:
                raise PersistenceConflictError(
                    "decision replay conflicts with the immutable ledger record"
                )
            return DecisionTrace.model_validate(existing.trace)

        session.add(
            DecisionRow(
                decision_id=trace.decision_id,
                event_id=trace.event_id,
                order_id=trace.order_id,
                trace=trace.model_dump(mode="json"),
                fingerprint=fingerprint,
                created_at=trace.created_at,
            )
        )
        session.flush()
        return trace

    def get(self, session: Session, decision_id: str) -> DecisionTrace | None:
        row = session.get(DecisionRow, decision_id)
        return None if row is None else DecisionTrace.model_validate(row.trace)

    def count(self, session: Session) -> int:
        return len(session.scalars(select(DecisionRow.decision_id)).all())

    def list_recent(
        self, session: Session, *, limit: int = 100
    ) -> tuple[DecisionTrace, ...]:
        rows = session.scalars(
            select(DecisionRow).order_by(DecisionRow.created_at.desc()).limit(limit)
        ).all()
        return tuple(DecisionTrace.model_validate(row.trace) for row in rows)


class ApprovalRepository:
    def create(self, session: Session, record: ApprovalRecord) -> ApprovalRecord:
        existing = session.get(ApprovalRow, record.approval_id)
        if existing is not None:
            persisted = self._to_model(existing)
            if canonical_fingerprint(persisted) != canonical_fingerprint(record):
                raise PersistenceConflictError("approval identity conflicts with existing record")
            return persisted

        session.add(
            ApprovalRow(
                approval_id=record.approval_id,
                decision_id=record.decision_id,
                requested_action=record.requested_action.value,
                status=record.status.value,
                requested_by=record.requested_by,
                requested_at=record.requested_at,
                expires_at=record.expires_at,
                decided_by=record.decided_by,
                decided_by_role=(record.decided_by_role.value if record.decided_by_role else None),
                decision_reason=record.decision_reason,
                decided_at=record.decided_at,
            )
        )
        session.flush()
        return record

    def get(self, session: Session, approval_id: str) -> ApprovalRecord | None:
        row = session.get(ApprovalRow, approval_id)
        return None if row is None else self._to_model(row)

    def get_by_decision(
        self, session: Session, decision_id: str
    ) -> ApprovalRecord | None:
        row = session.scalar(
            select(ApprovalRow)
            .where(ApprovalRow.decision_id == decision_id)
            .order_by(ApprovalRow.requested_at.desc())
        )
        return None if row is None else self._to_model(row)

    def update(self, session: Session, record: ApprovalRecord) -> ApprovalRecord:
        row = session.get(ApprovalRow, record.approval_id)
        if row is None:
            raise RecordNotFoundError(f"approval {record.approval_id!r} not found")
        row.status = record.status.value
        row.decided_by = record.decided_by
        row.decided_by_role = record.decided_by_role.value if record.decided_by_role else None
        row.decision_reason = record.decision_reason
        row.decided_at = record.decided_at
        session.flush()
        return record

    def list_pending(self, session: Session) -> tuple[ApprovalRecord, ...]:
        rows = session.scalars(
            select(ApprovalRow)
            .where(ApprovalRow.status == ApprovalStatus.PENDING.value)
            .order_by(ApprovalRow.requested_at)
        ).all()
        return tuple(self._to_model(row) for row in rows)

    @staticmethod
    def _to_model(row: ApprovalRow) -> ApprovalRecord:
        return ApprovalRecord(
            approval_id=row.approval_id,
            decision_id=row.decision_id,
            requested_action=row.requested_action,
            status=row.status,
            requested_by=row.requested_by,
            requested_at=ensure_utc(row.requested_at),
            expires_at=ensure_utc(row.expires_at),
            decided_by=row.decided_by,
            decided_by_role=row.decided_by_role,
            decision_reason=row.decision_reason,
            decided_at=ensure_utc(row.decided_at),
        )


class ActionRepository:
    def record(self, session: Session, execution: ActionExecution) -> ActionExecution:
        fingerprint = canonical_fingerprint(execution.command)
        existing = session.scalar(
            select(ActionRow).where(ActionRow.idempotency_key == execution.command.idempotency_key)
        )
        if existing is not None:
            if existing.fingerprint != fingerprint:
                raise PersistenceConflictError(
                    "idempotency key was reused for a different action command"
                )
            return self._to_model(existing)

        session.add(
            ActionRow(
                action_id=execution.action_id,
                decision_id=execution.command.decision_id,
                order_id=execution.command.order_id,
                action=execution.command.action.value,
                idempotency_key=execution.command.idempotency_key,
                status=execution.status.value,
                command=execution.command.model_dump(mode="json"),
                steps=[step.model_dump(mode="json") for step in execution.steps],
                fingerprint=fingerprint,
                started_at=execution.started_at,
                completed_at=execution.completed_at,
                error_code=execution.error_code,
                manual_recovery_reason=execution.manual_recovery_reason,
            )
        )
        session.flush()
        return execution

    def update(self, session: Session, execution: ActionExecution) -> ActionExecution:
        row = session.get(ActionRow, execution.action_id)
        if row is None:
            raise RecordNotFoundError(f"action {execution.action_id!r} not found")
        row.status = execution.status.value
        row.steps = [step.model_dump(mode="json") for step in execution.steps]
        row.completed_at = execution.completed_at
        row.error_code = execution.error_code
        row.manual_recovery_reason = execution.manual_recovery_reason
        session.flush()
        return execution

    def get(self, session: Session, action_id: str) -> ActionExecution | None:
        row = session.get(ActionRow, action_id)
        return None if row is None else self._to_model(row)

    def get_by_decision(self, session: Session, decision_id: str) -> ActionExecution | None:
        row = session.scalar(
            select(ActionRow)
            .where(ActionRow.decision_id == decision_id)
            .order_by(ActionRow.started_at.desc())
        )
        return None if row is None else self._to_model(row)

    @staticmethod
    def _to_model(row: ActionRow) -> ActionExecution:
        return ActionExecution.model_validate(
            {
                "action_id": row.action_id,
                "command": row.command,
                "status": row.status,
                "steps": row.steps,
                "started_at": ensure_utc(row.started_at),
                "completed_at": ensure_utc(row.completed_at),
                "error_code": row.error_code,
                "manual_recovery_reason": row.manual_recovery_reason,
            }
        )


class OutcomeRepository:
    def record(self, session: Session, outcome: OutcomeVerification) -> OutcomeVerification:
        fingerprint = canonical_fingerprint(outcome)
        existing = session.scalar(
            select(OutcomeRow).where(OutcomeRow.decision_id == outcome.decision_id)
        )
        if existing is not None:
            if existing.fingerprint != fingerprint:
                raise PersistenceConflictError(
                    "decision already has a conflicting verified outcome"
                )
            return self._to_model(existing)

        session.add(
            OutcomeRow(
                outcome_id=outcome.outcome_id,
                decision_id=outcome.decision_id,
                action_id=outcome.action_id,
                status=outcome.status.value,
                verified_at=outcome.verified_at,
                on_time_delivery_observed=outcome.on_time_delivery_observed,
                actual_intervention_cost=outcome.actual_intervention_cost,
                realised_gross_margin=outcome.realised_gross_margin,
                estimated_incremental_value=outcome.estimated_incremental_value,
                evidence_references=[
                    ref.model_dump(mode="json")
                    for ref in outcome.evidence_references
                ],
                details=outcome.details,
                fingerprint=fingerprint,
            )
        )
        session.flush()
        return outcome

    def get_by_decision(self, session: Session, decision_id: str) -> OutcomeVerification | None:
        row = session.scalar(select(OutcomeRow).where(OutcomeRow.decision_id == decision_id))
        return None if row is None else self._to_model(row)

    @staticmethod
    def _to_model(row: OutcomeRow) -> OutcomeVerification:
        return OutcomeVerification(
            outcome_id=row.outcome_id,
            decision_id=row.decision_id,
            action_id=row.action_id,
            status=row.status,
            verified_at=ensure_utc(row.verified_at),
            on_time_delivery_observed=row.on_time_delivery_observed,
            actual_intervention_cost=row.actual_intervention_cost,
            realised_gross_margin=row.realised_gross_margin,
            estimated_incremental_value=row.estimated_incremental_value,
            evidence_references=tuple(row.evidence_references),
            details=row.details,
        )
