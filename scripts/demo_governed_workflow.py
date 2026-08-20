"""Demonstrate approval, action execution and verified outcome recording."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from promiseguard.config import Settings
from promiseguard.models import (
    ApprovalDecisionInput,
    DeliveryObservation,
    OperatingMode,
    RecoveryAction,
    SourceReference,
    UserRole,
)
from promiseguard.services import ServiceContainer
from promiseguard.synthetic import SyntheticDataGenerator


def main() -> None:
    services = ServiceContainer.build(
        Settings(
            database_url="sqlite+pysqlite:///:memory:",
            environment="demo",
            auto_create_schema=True,
        )
    )
    try:
        record, decision = _intervention_case(services)
        submitted = services.workflow.submit(
            decision.decision_id,
            actor_id="analyst-demo",
        )
        if submitted.approval is None:
            raise RuntimeError("demo case did not create a required approval")

        services.workflow.approve_and_execute(
            submitted.approval.approval_id,
            ApprovalDecisionInput(
                actor_id="manager-demo",
                actor_role=UserRole.OPERATIONS_MANAGER,
                reason="Demo approval after reviewing evidence",
            ),
        )
        observation_time = datetime.now(UTC)
        verified = services.workflow.verify(
            decision.decision_id,
            observation=DeliveryObservation(
                order_id=record.request.order.order_id,
                delivered_on_time=True,
                observed_at=observation_time,
                source_reference=SourceReference(
                    system="carrier-simulator",
                    record_id=f"delivered:{record.request.order.order_id}",
                    observed_at=observation_time,
                ),
            ),
        )
        print(json.dumps(verified.model_dump(mode="json"), indent=2, sort_keys=True))
    finally:
        services.close()


def _intervention_case(services: ServiceContainer):
    records = SyntheticDataGenerator(seed=9).generate(
        500,
        mode=OperatingMode.APPROVAL,
    )
    for record in records:
        decision = services.evaluation.evaluate(record.request)
        if decision.recommendation.selected_action in {
            RecoveryAction.REROUTE,
            RecoveryAction.CARRIER_UPGRADE,
            RecoveryAction.SPLIT_SHIPMENT,
        }:
            return record, decision
    raise RuntimeError("no executable intervention case found in deterministic sample")


if __name__ == "__main__":
    main()
