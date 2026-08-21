"""Durable operator feedback for shadow and approval-mode review."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from promiseguard.database import Database
from promiseguard.identity import bind_claimed_role
from promiseguard.ledger import SqlDecisionLedger
from promiseguard.models import OperatorFeedback, OperatorFeedbackInput
from promiseguard.persistence import FeedbackRepository, RecordNotFoundError


class FeedbackService:
    def __init__(self, database: Database, ledger: SqlDecisionLedger) -> None:
        self.database = database
        self.ledger = ledger
        self.repository = FeedbackRepository()

    def record(self, decision_id: str, payload: OperatorFeedbackInput) -> OperatorFeedback:
        if self.ledger.get(decision_id) is None:
            raise RecordNotFoundError(f"decision {decision_id!r} not found")
        bind_claimed_role(payload.actor_id, payload.actor_role)
        created_at = datetime.now(UTC)
        material = "|".join(
            (
                decision_id,
                payload.actor_id,
                created_at.isoformat(),
                payload.comment,
            )
        )
        feedback = OperatorFeedback(
            feedback_id=f"fb_{sha256(material.encode()).hexdigest()[:24]}",
            decision_id=decision_id,
            actor_id=payload.actor_id,
            actor_role=payload.actor_role,
            useful=payload.useful,
            expected_outcome_matched=payload.expected_outcome_matched,
            comment=payload.comment,
            created_at=created_at,
        )
        with self.database.session() as session:
            return self.repository.record(session, feedback)

    def list_for_decision(self, decision_id: str) -> tuple[OperatorFeedback, ...]:
        if self.ledger.get(decision_id) is None:
            raise RecordNotFoundError(f"decision {decision_id!r} not found")
        with self.database.session() as session:
            return self.repository.list_for_decision(session, decision_id)
