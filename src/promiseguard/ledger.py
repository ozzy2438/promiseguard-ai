"""In-memory immutable decision ledger for deterministic vertical-slice evidence."""

from __future__ import annotations

import json
from hashlib import sha256

from promiseguard.models import DecisionTrace


class LedgerConflictError(RuntimeError):
    """Raised when the same decision identifier is replayed with different content."""


class InMemoryDecisionLedger:
    """Store immutable decision traces with idempotent replay semantics."""

    def __init__(self) -> None:
        self._records: dict[str, DecisionTrace] = {}
        self._fingerprints: dict[str, str] = {}

    def record(self, trace: DecisionTrace) -> DecisionTrace:
        fingerprint = self._fingerprint(trace)
        existing = self._records.get(trace.decision_id)
        if existing is None:
            self._records[trace.decision_id] = trace
            self._fingerprints[trace.decision_id] = fingerprint
            return trace

        if self._fingerprints[trace.decision_id] != fingerprint:
            raise LedgerConflictError(
                "decision replay conflicts with the immutable ledger record"
            )
        return existing

    def get(self, decision_id: str) -> DecisionTrace | None:
        return self._records.get(decision_id)

    def count(self) -> int:
        return len(self._records)

    @staticmethod
    def _fingerprint(trace: DecisionTrace) -> str:
        canonical = json.dumps(
            trace.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(canonical.encode("utf-8")).hexdigest()
