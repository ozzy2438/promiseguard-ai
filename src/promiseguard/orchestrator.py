"""Closed-loop PromiseGuard orchestration for deterministic decisioning."""

from __future__ import annotations

from hashlib import sha256

from promiseguard.ledger import DecisionLedger, InMemoryDecisionLedger
from promiseguard.models import (
    DecisionStatus,
    DecisionTrace,
    EvaluationRequest,
    OperatingMode,
    PolicyEvaluation,
)
from promiseguard.optimizer import DecisionOptimizer
from promiseguard.policy import PolicyGateway
from promiseguard.risk import DeterministicRiskScorer, RiskScorer
from promiseguard.simulator import RecoverySimulator


class PromiseGuardOrchestrator:
    """Run one order event through risk, simulation, optimisation, policy and ledger."""

    trace_version = "decision-trace-v2"

    def __init__(
        self,
        *,
        scorer: RiskScorer | None = None,
        simulator: RecoverySimulator | None = None,
        optimiser: DecisionOptimizer | None = None,
        policy: PolicyGateway | None = None,
        ledger: DecisionLedger | None = None,
    ) -> None:
        self.scorer = scorer or DeterministicRiskScorer()
        self.simulator = simulator or RecoverySimulator()
        self.optimiser = optimiser or DecisionOptimizer()
        self.policy = policy or PolicyGateway()
        self.ledger = ledger or InMemoryDecisionLedger()

    def evaluate(self, request: EvaluationRequest) -> DecisionTrace:
        risk = self.scorer.score(request.order)
        options = self.simulator.simulate(request.order, risk)
        recommendation = self.optimiser.select(options)
        policy = self.policy.evaluate(
            order=request.order,
            risk=risk,
            recommendation=recommendation,
            mode=request.mode,
        )

        decision_id = self._decision_id(request, policy)
        status = self._status_for_mode(request.mode)
        trace = DecisionTrace(
            trace_version=self.trace_version,
            decision_id=decision_id,
            event_id=request.event.event_id,
            order_id=request.order.order_id,
            mode=request.mode,
            risk=risk,
            recommendation=recommendation,
            policy=policy,
            status=status,
            created_at=request.order.evaluation_time,
            tenant_id=request.order.tenant_id,
        )
        return self.ledger.record(trace)

    def _decision_id(self, request: EvaluationRequest, policy: PolicyEvaluation) -> str:
        identity = "|".join(
            (
                request.event.deduplication_key,
                str(request.event.event_version),
                request.order.order_id,
                self.scorer.model_version,
                self.simulator.simulator_version,
                self.optimiser.optimiser_version,
                self.policy.policy_version,
                policy.control_version,
                policy.disposition.value,
                str(policy.execution_allowed),
                ",".join(policy.reasons),
                request.mode.value,
            )
        )
        return f"dec_{sha256(identity.encode('utf-8')).hexdigest()[:24]}"

    @staticmethod
    def _status_for_mode(mode: OperatingMode) -> DecisionStatus:
        return {
            OperatingMode.OBSERVE: DecisionStatus.OBSERVED,
            OperatingMode.SHADOW: DecisionStatus.SHADOW_RECORDED,
            OperatingMode.RECOMMENDATION: DecisionStatus.RECOMMENDED,
            OperatingMode.APPROVAL: DecisionStatus.AWAITING_APPROVAL,
            OperatingMode.BOUNDED_AUTONOMY: DecisionStatus.READY_FOR_EXECUTION,
        }[mode]
