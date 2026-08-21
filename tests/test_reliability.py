from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from promiseguard.approval import ApprovalError
from promiseguard.config import Settings
from promiseguard.execution import ActionExecutionError
from promiseguard.models import (
    ActionStatus,
    ApprovalDecisionInput,
    ApprovalStatus,
    DeliveryObservation,
    EvaluationRequest,
    KillSwitchUpdateInput,
    OperatingMode,
    RecoveryAction,
    SourceReference,
    UserRole,
    VerificationStatus,
)
from promiseguard.openai_agent import OpenAIAgentService, OpenAIAgentUnavailableError
from promiseguard.openai_budget import OpenAIPerRunLimitError
from promiseguard.openai_models import AgentRunRequest
from promiseguard.persistence import PersistenceConflictError
from promiseguard.services import ServiceContainer


def _file_services(tmp_path: Path) -> ServiceContainer:
    return ServiceContainer.build(
        Settings(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'reliability.db'}",
            environment="test",
            auto_create_schema=True,
        )
    )


def _observation(order_id: str, observed_at) -> DeliveryObservation:
    return DeliveryObservation(
        order_id=order_id,
        delivered_on_time=True,
        observed_at=observed_at,
        source_reference=SourceReference(
            system="carrier",
            record_id=f"delivered:{order_id}",
            observed_at=observed_at,
        ),
    )


def test_duplicate_source_event_is_idempotent(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
) -> None:
    first = services.evaluation.evaluate(at_risk_request)
    second = services.evaluation.evaluate(at_risk_request)
    assert first.decision_id == second.decision_id
    assert services.ledger.count() == 1


def test_duplicate_source_event_with_changed_payload_is_rejected(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
) -> None:
    services.evaluation.evaluate(at_risk_request)
    mutated = at_risk_request.model_copy(
        update={
            "order": at_risk_request.order.model_copy(update={"gross_margin": Decimal("99.00")})
        }
    )
    with pytest.raises(PersistenceConflictError):
        services.evaluation.evaluate(mutated)


def test_concurrent_approvals_only_one_succeeds(
    tmp_path: Path,
    at_risk_request: EvaluationRequest,
    evaluation_time,
) -> None:
    services = _file_services(tmp_path)
    try:
        trace = services.evaluation.evaluate(
            at_risk_request.model_copy(update={"mode": OperatingMode.APPROVAL})
        )
        pending = services.workflow.submit(
            trace.decision_id,
            actor_id="analyst-1",
            now=evaluation_time,
        ).approval
        assert pending is not None

        def _attempt(actor_id: str) -> str:
            try:
                state = services.workflow.approve_and_execute(
                    pending.approval_id,
                    ApprovalDecisionInput(
                        actor_id=actor_id,
                        actor_role=UserRole.OPERATIONS_MANAGER,
                        reason="Concurrent approval race",
                    ),
                    now=evaluation_time + timedelta(minutes=1),
                )
                assert state.execution is not None
                return state.execution.status.value
            except ApprovalError:
                return "REJECTED_RACE"

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(_attempt, "manager-1"),
                pool.submit(_attempt, "manager-2"),
            ]
            results = [future.result() for future in as_completed(futures)]
        assert results.count("SUCCEEDED") == 1
        assert results.count("REJECTED_RACE") == 1
        persisted = services.approvals.get(pending.approval_id)
        assert persisted is not None
        assert persisted.status is ApprovalStatus.APPROVED
    finally:
        services.close()


def test_concurrent_decisions_for_distinct_orders_both_persist(
    tmp_path: Path,
    at_risk_request: EvaluationRequest,
) -> None:
    services = _file_services(tmp_path)
    try:

        def _evaluate(suffix: str):
            request = at_risk_request.model_copy(
                update={
                    "event": at_risk_request.event.model_copy(
                        update={
                            "event_id": f"evt-concurrent-{suffix}",
                            "deduplication_key": f"oms:evt-concurrent-{suffix}:v1",
                        }
                    ),
                    "order": at_risk_request.order.model_copy(
                        update={"order_id": f"order-concurrent-{suffix}"}
                    ),
                }
            )
            return services.evaluation.evaluate(request).decision_id

        with ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(_evaluate, ["a", "b", "c", "d"]))
        assert len(set(ids)) == 4
        assert services.ledger.count() == 4
    finally:
        services.close()


def test_workflow_survives_process_restart_and_verifies(
    tmp_path: Path,
    at_risk_request: EvaluationRequest,
    evaluation_time,
) -> None:
    url = f"sqlite+pysqlite:///{tmp_path / 'restart.db'}"
    first = ServiceContainer.build(
        Settings(database_url=url, environment="test", auto_create_schema=True)
    )
    try:
        trace = first.evaluation.evaluate(
            at_risk_request.model_copy(update={"mode": OperatingMode.APPROVAL})
        )
        pending = first.workflow.submit(
            trace.decision_id, actor_id="analyst-1", now=evaluation_time
        ).approval
        assert pending is not None
        decision_id = trace.decision_id
        approval_id = pending.approval_id
    finally:
        first.close()

    recovered = ServiceContainer.build(
        Settings(database_url=url, environment="test", auto_create_schema=True)
    )
    try:
        loaded = recovered.ledger.get(decision_id)
        assert loaded is not None
        executed = recovered.workflow.approve_and_execute(
            approval_id,
            ApprovalDecisionInput(
                actor_id="manager-1",
                actor_role=UserRole.OPERATIONS_MANAGER,
                reason="Resume after process restart",
            ),
            now=evaluation_time + timedelta(minutes=1),
        )
        assert executed.execution is not None
        assert executed.execution.status is ActionStatus.SUCCEEDED
    finally:
        recovered.close()

    after_execute = ServiceContainer.build(
        Settings(database_url=url, environment="test", auto_create_schema=True)
    )
    try:
        verified = after_execute.workflow.verify(
            decision_id,
            observation=_observation(
                at_risk_request.order.order_id,
                evaluation_time + timedelta(days=1),
            ),
            now=evaluation_time + timedelta(days=1),
        )
        assert verified.outcome is not None
        assert verified.outcome.status is VerificationStatus.VERIFIED
    finally:
        after_execute.close()


def test_temporary_database_interruption_then_recovery(
    tmp_path: Path,
    at_risk_request: EvaluationRequest,
) -> None:
    db_path = tmp_path / "interrupt.db"
    url = f"sqlite+pysqlite:///{db_path}"
    services = ServiceContainer.build(
        Settings(database_url=url, environment="test", auto_create_schema=True)
    )
    trace = services.evaluation.evaluate(at_risk_request)
    services.database.dispose()
    offline = db_path.with_suffix(".offline")
    db_path.rename(offline)
    with pytest.raises(OperationalError):
        services.ledger.get(trace.decision_id)
    offline.rename(db_path)
    recovered = ServiceContainer.build(
        Settings(database_url=url, environment="test", auto_create_schema=True)
    )
    try:
        assert recovered.ledger.get(trace.decision_id) is not None
    finally:
        recovered.close()


def test_stale_kill_switch_blocks_execution_after_approval_created(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
    evaluation_time,
) -> None:
    trace = services.evaluation.evaluate(
        at_risk_request.model_copy(update={"mode": OperatingMode.APPROVAL})
    )
    pending = services.workflow.submit(
        trace.decision_id, actor_id="analyst-1", now=evaluation_time
    ).approval
    assert pending is not None
    services.autonomy.set_kill_switch(
        KillSwitchUpdateInput(
            active=True,
            actor_id="manager-1",
            actor_role=UserRole.OPERATIONS_MANAGER,
            reason="Activated after approval was created",
        )
    )
    with pytest.raises(ActionExecutionError, match="kill switch"):
        services.workflow.approve_and_execute(
            pending.approval_id,
            ApprovalDecisionInput(
                actor_id="manager-1",
                actor_role=UserRole.OPERATIONS_MANAGER,
                reason="Should be blocked by kill switch",
            ),
            now=evaluation_time + timedelta(minutes=1),
        )


def test_unavailable_llm_does_not_spend_or_advance_workflow(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
) -> None:
    decision = services.evaluation.evaluate(at_risk_request)
    agent = OpenAIAgentService(
        workflow=services.workflow,
        budget=services.openai_budget,
        model="gpt-5-nano",
        max_output_tokens=320,
        timeout_seconds=10,
        enabled=False,
    )
    with pytest.raises(OpenAIAgentUnavailableError):
        agent.run(AgentRunRequest(decision_id=decision.decision_id, actor_id="analyst-openai"))
    assert services.openai_budget.state().spent_usd == 0
    assert services.workflow.get_state(decision.decision_id).approval is None


def test_exhausted_openai_budget_is_refused_before_provider_call(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
) -> None:
    decision = services.evaluation.evaluate(
        at_risk_request.model_copy(
            update={
                "event": at_risk_request.event.model_copy(
                    update={
                        "event_id": "evt-budget-exhausted",
                        "deduplication_key": "oms:evt-budget-exhausted:v1",
                    }
                ),
                "order": at_risk_request.order.model_copy(update={"order_id": "order-budget"}),
            }
        )
    )
    with pytest.raises(OpenAIPerRunLimitError):
        services.openai_budget.reserve(
            decision_id=decision.decision_id,
            model="gpt-5-nano",
            prompt_version="reliability-v1",
            context_fingerprint="c" * 64,
            estimated_cost_usd=Decimal("3.01"),
        )
    assert services.openai_budget.state().spent_usd == 0
    assert services.openai_budget.state().limit_usd == Decimal("3.00")


def test_split_ambiguous_timeout_is_verified_before_retry(
    services: ServiceContainer,
    at_risk_request: EvaluationRequest,
    evaluation_time,
) -> None:
    split_order = at_risk_request.order.model_copy(
        update={
            "alternative_location_available": False,
            "alternative_location_id": None,
            "carrier_upgrade_on_time_probability": 0.40,
            "carrier_upgrade_cost": Decimal("40.00"),
            "split_shipment_possible": True,
            "split_shipment_on_time_probability": 0.97,
            "split_shipment_cost": Decimal("4.00"),
        }
    )
    request = at_risk_request.model_copy(
        update={
            "event": at_risk_request.event.model_copy(
                update={
                    "event_id": "evt-split-timeout",
                    "deduplication_key": "oms:evt-split-timeout:v1",
                }
            ),
            "order": split_order,
            "mode": OperatingMode.APPROVAL,
        }
    )
    trace = services.evaluation.evaluate(request)
    assert trace.recommendation.selected_action is RecoveryAction.SPLIT_SHIPMENT
    pending = services.workflow.submit(
        trace.decision_id, actor_id="analyst-1", now=evaluation_time
    ).approval
    assert pending is not None
    services.adapter.inject_failure("create_split", when="after")
    state = services.workflow.approve_and_execute(
        pending.approval_id,
        ApprovalDecisionInput(
            actor_id="manager-1",
            actor_role=UserRole.OPERATIONS_MANAGER,
            reason="Lost acknowledgement after split write",
        ),
        now=evaluation_time + timedelta(minutes=1),
    )
    assert state.execution is not None
    assert state.execution.status is ActionStatus.SUCCEEDED
    assert state.execution.steps[0].provider_reference == (
        f"verified-after-timeout:{request.order.order_id}"
    )
    assert request.order.order_id in services.adapter.split_shipments
