"""Prometheus metrics for decisions, controls, OpenAI reviews and outcomes."""

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
        self.openai_runs = Counter(
            "promiseguard_openai_runs_total",
            "Bounded OpenAI review runs by final status and model.",
            ("status", "model"),
            registry=self.registry,
        )
        self.openai_budget_blocks = Counter(
            "promiseguard_openai_budget_blocks_total",
            "OpenAI requests blocked locally before provider invocation.",
            ("reason",),
            registry=self.registry,
        )
        self.openai_cost_usd = Counter(
            "promiseguard_openai_cost_usd_total",
            "Application-accounted OpenAI cost in US dollars.",
            ("model",),
            registry=self.registry,
        )
        self.openai_latency = Histogram(
            "promiseguard_openai_review_latency_seconds",
            "Bounded OpenAI structured-review latency.",
            ("model",),
            registry=self.registry,
        )
