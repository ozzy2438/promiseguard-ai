"""Prometheus metrics for decisions, approvals, execution and verification."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram


class PromiseGuardMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry(auto_describe=True)
        self.decisions = Counter(
            "promiseguard_decisions_total",
            "Decision evaluations by policy disposition.",
            ("disposition", "mode"),
            registry=self.registry,
        )
        self.approvals = Counter(
            "promiseguard_approvals_total",
            "Approval transitions.",
            ("status",),
            registry=self.registry,
        )
        self.actions = Counter(
            "promiseguard_actions_total",
            "Governed actions by type and final status.",
            ("action", "status"),
            registry=self.registry,
        )
        self.verifications = Counter(
            "promiseguard_verifications_total",
            "Outcome verifications by status.",
            ("status",),
            registry=self.registry,
        )
        self.decision_latency = Histogram(
            "promiseguard_decision_latency_seconds",
            "End-to-end deterministic decision latency.",
            registry=self.registry,
        )
