"""Explicit one-call live smoke test for the bounded OpenAI review layer."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from decimal import Decimal

from promiseguard.config import Settings
from promiseguard.models import OperatingMode, RecoveryAction
from promiseguard.openai_models import AgentRunRequest
from promiseguard.services import ServiceContainer
from promiseguard.synthetic import SyntheticDataGenerator


def main() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not available in this shell")

    configured = Settings.from_env()
    # The smoke path can never enlarge the user's requested three-dollar ceiling.
    settings = replace(
        configured,
        database_url="sqlite+pysqlite:///:memory:",
        environment="openai-smoke",
        auto_create_schema=True,
        openai_enabled=True,
        openai_budget_usd=min(configured.openai_budget_usd, Decimal("3.00")),
        openai_per_run_limit_usd=min(configured.openai_per_run_limit_usd, Decimal("0.001")),
    )
    services = ServiceContainer.build(settings)
    try:
        decision_id = _create_reviewable_decision(services)
        result = services.openai_agent.run(
            AgentRunRequest(
                decision_id=decision_id,
                actor_id="openai-smoke",
                advance_workflow=False,
            )
        )
        payload = {
            "run_id": result.run.run_id,
            "status": result.run.status.value,
            "model": result.run.model,
            "prompt_version": result.run.prompt_version,
            "actual_cost_usd": str(result.run.actual_cost_usd),
            "usage": (
                result.run.usage.model_dump(mode="json") if result.run.usage is not None else None
            ),
            "budget": result.budget.model_dump(mode="json"),
            "review": (
                result.run.review.model_dump(mode="json") if result.run.review is not None else None
            ),
            "reused_existing_run": result.reused_existing_run,
            "workflow_advanced": result.workflow is not None,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    finally:
        services.close()


def _create_reviewable_decision(services: ServiceContainer) -> str:
    records = SyntheticDataGenerator(seed=20260820).generate(
        500,
        mode=OperatingMode.APPROVAL,
    )
    executable = {
        RecoveryAction.REROUTE,
        RecoveryAction.CARRIER_UPGRADE,
        RecoveryAction.SPLIT_SHIPMENT,
    }
    for record in records:
        decision = services.evaluation.evaluate(record.request)
        if decision.recommendation.selected_action in executable:
            return decision.decision_id
    raise RuntimeError("deterministic sample did not contain a reviewable intervention")


if __name__ == "__main__":
    main()
