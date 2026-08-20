"""Durable evaluation service that persists inputs before recording decisions."""

from __future__ import annotations

from promiseguard.database import Database
from promiseguard.models import DecisionTrace, EvaluationRequest
from promiseguard.orchestrator import PromiseGuardOrchestrator
from promiseguard.persistence import EventRepository


class EvaluationService:
    """Persist a source event and run the deterministic decision pipeline."""

    def __init__(self, database: Database, orchestrator: PromiseGuardOrchestrator) -> None:
        self.database = database
        self.orchestrator = orchestrator
        self.events = EventRepository()

    def evaluate(self, request: EvaluationRequest) -> DecisionTrace:
        with self.database.session() as session:
            self.events.ingest(
                session,
                event=request.event,
                payload=request.model_dump(mode="json"),
            )
        return self.orchestrator.evaluate(request)
