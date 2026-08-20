"""Dependency container for the local and production-like application runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from promiseguard.approval import ApprovalService
from promiseguard.autonomy import AutonomyController
from promiseguard.config import Settings
from promiseguard.database import Database
from promiseguard.evaluation import EvaluationService
from promiseguard.execution import ActionGateway, SimulatedOperationsAdapter
from promiseguard.ledger import SqlDecisionLedger
from promiseguard.metrics import PromiseGuardMetrics
from promiseguard.orchestrator import PromiseGuardOrchestrator
from promiseguard.policy import PolicyGateway
from promiseguard.risk import DeterministicRiskScorer, RiskScorer
from promiseguard.trained_risk import TrainedRiskScorer
from promiseguard.verification import OutcomeVerificationService
from promiseguard.workflow import RecoveryWorkflowService


@dataclass(slots=True)
class ServiceContainer:
    settings: Settings
    database: Database
    autonomy: AutonomyController
    ledger: SqlDecisionLedger
    orchestrator: PromiseGuardOrchestrator
    evaluation: EvaluationService
    adapter: SimulatedOperationsAdapter
    approvals: ApprovalService
    actions: ActionGateway
    verification: OutcomeVerificationService
    workflow: RecoveryWorkflowService
    metrics: PromiseGuardMetrics

    @classmethod
    def build(cls, settings: Settings | None = None) -> ServiceContainer:
        resolved = settings or Settings.from_env()
        database = Database(resolved.database_url)
        if resolved.auto_create_schema:
            database.create_schema()

        autonomy = AutonomyController(database)
        policy = PolicyGateway(
            kill_switch_active=lambda: autonomy.kill_switch().active,
            autonomy_allowed=autonomy.execution_permitted,
            control_version=autonomy.context_version,
        )
        ledger = SqlDecisionLedger(database)
        scorer = cls._scorer_from_environment()
        orchestrator = PromiseGuardOrchestrator(
            scorer=scorer,
            policy=policy,
            ledger=ledger,
        )
        evaluation = EvaluationService(database, orchestrator)
        adapter = SimulatedOperationsAdapter()
        approvals = ApprovalService(database)
        actions = ActionGateway(database, adapter, autonomy)
        verification = OutcomeVerificationService(database, adapter, autonomy)
        workflow = RecoveryWorkflowService(
            database=database,
            ledger=ledger,
            approvals=approvals,
            actions=actions,
            verification=verification,
        )
        return cls(
            settings=resolved,
            database=database,
            autonomy=autonomy,
            ledger=ledger,
            orchestrator=orchestrator,
            evaluation=evaluation,
            adapter=adapter,
            approvals=approvals,
            actions=actions,
            verification=verification,
            workflow=workflow,
            metrics=PromiseGuardMetrics(),
        )

    def close(self) -> None:
        self.database.dispose()

    @staticmethod
    def _scorer_from_environment() -> RiskScorer:
        artifact = os.getenv("RISK_MODEL_PATH")
        if artifact and Path(artifact).exists():
            return TrainedRiskScorer(artifact)
        return DeterministicRiskScorer()
