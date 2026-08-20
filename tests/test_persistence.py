from __future__ import annotations

from decimal import Decimal

import pytest

from promiseguard.database import Database
from promiseguard.evaluation import EvaluationService
from promiseguard.ledger import LedgerConflictError, SqlDecisionLedger
from promiseguard.models import EvaluationRequest
from promiseguard.orchestrator import PromiseGuardOrchestrator
from promiseguard.persistence import PersistenceConflictError


@pytest.fixture
def database() -> Database:
    database = Database("sqlite+pysqlite:///:memory:")
    database.create_schema()
    yield database
    database.dispose()


def test_decision_survives_new_ledger_instance(
    database: Database, at_risk_request: EvaluationRequest
) -> None:
    first_ledger = SqlDecisionLedger(database)
    service = EvaluationService(
        database,
        PromiseGuardOrchestrator(ledger=first_ledger),
    )

    trace = service.evaluate(at_risk_request)
    second_ledger = SqlDecisionLedger(database)

    assert second_ledger.get(trace.decision_id) == trace
    assert second_ledger.count() == 1


def test_event_inbox_rejects_conflicting_replay(
    database: Database, at_risk_request: EvaluationRequest
) -> None:
    service = EvaluationService(
        database,
        PromiseGuardOrchestrator(ledger=SqlDecisionLedger(database)),
    )
    service.evaluate(at_risk_request)
    changed = at_risk_request.model_copy(
        update={
            "order": at_risk_request.order.model_copy(
                update={"gross_margin": Decimal("999.00")}
            )
        }
    )

    with pytest.raises(PersistenceConflictError):
        service.evaluate(changed)


def test_sql_decision_ledger_rejects_conflicting_trace(
    database: Database, at_risk_request: EvaluationRequest
) -> None:
    ledger = SqlDecisionLedger(database)
    orchestrator = PromiseGuardOrchestrator(ledger=ledger)
    orchestrator.evaluate(at_risk_request)
    changed = at_risk_request.model_copy(
        update={
            "order": at_risk_request.order.model_copy(
                update={"reroute_cost": Decimal("10.25")}
            )
        }
    )

    with pytest.raises(LedgerConflictError):
        orchestrator.evaluate(changed)
