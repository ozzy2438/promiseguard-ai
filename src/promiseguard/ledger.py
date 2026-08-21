"""Decision-ledger implementations with immutable replay semantics."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Protocol

from promiseguard.database import Database
from promiseguard.models import DecisionTrace
from promiseguard.persistence import DecisionRepository, PersistenceConflictError


class LedgerConflictError(RuntimeError):
    """Raised when the same decision identifier is replayed with different content."""


class DecisionLedger(Protocol):
    def record(self, trace: DecisionTrace) -> DecisionTrace: ...

    def get(self, decision_id: str) -> DecisionTrace | None: ...

    def count(self) -> int: ...


def canonical_fingerprint(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(canonical.encode("utf-8")).hexdigest()


class InMemoryDecisionLedger:
    """Store immutable decision traces with idempotent replay semantics."""

    def __init__(self) -> None:
        self._records: dict[str, DecisionTrace] = {}
        self._fingerprints: dict[str, str] = {}

    def record(self, trace: DecisionTrace) -> DecisionTrace:
        fingerprint = canonical_fingerprint(trace.model_dump(mode="json"))
        existing = self._records.get(trace.decision_id)
        if existing is None:
            self._records[trace.decision_id] = trace
            self._fingerprints[trace.decision_id] = fingerprint
            return trace

        if self._fingerprints[trace.decision_id] != fingerprint:
            raise LedgerConflictError("decision replay conflicts with the immutable ledger record")
        return existing

    def get(self, decision_id: str) -> DecisionTrace | None:
        return self._records.get(decision_id)

    def count(self) -> int:
        return len(self._records)


class SqlDecisionLedger:
    """Persist immutable decision traces in a relational database."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.repository = DecisionRepository()

    def record(self, trace: DecisionTrace) -> DecisionTrace:
        try:
            with self.database.session() as session:
                return self.repository.record(session, trace)
        except PersistenceConflictError as exc:
            raise LedgerConflictError(str(exc)) from exc

    def get(self, decision_id: str) -> DecisionTrace | None:
        with self.database.session() as session:
            return self.repository.get(session, decision_id)

    def count(self) -> int:
        with self.database.session() as session:
            return self.repository.count(session)

    def list_recent(self, *, limit: int = 100) -> tuple[DecisionTrace, ...]:
        with self.database.session() as session:
            return self.repository.list_recent(session, limit=limit)
