"""Reproducible synthetic fulfilment environment with known counterfactual ground truth."""

from __future__ import annotations

import json
import math
import random
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from promiseguard.models import (
    EvaluationRequest,
    OperationalEvent,
    OperatingMode,
    OrderContext,
    RecoveryAction,
    SourceReference,
    SyntheticGroundTruth,
    SyntheticRecord,
)

_CENTS = Decimal("0.01")


def _money(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _clip(value: float, minimum: float = 0.01, maximum: float = 0.99) -> float:
    return round(min(max(value, minimum), maximum), 4)


class SyntheticDataGenerator:
    """Generate point-in-time order contexts and counterfactual outcomes."""

    fulfilment_centres = ("FC-MEL", "FC-SYD", "FC-BNE")
    stores = tuple(f"STORE-{index:02d}" for index in range(1, 16))
    carriers = {
        "AUSPOST_STANDARD": 0.89,
        "STARTRACK_STANDARD": 0.93,
    }

    def __init__(self, *, seed: int = 20260820) -> None:
        self.seed = seed
        self.random = random.Random(seed)

    def generate(
        self,
        count: int,
        *,
        start_at: datetime | None = None,
        mode: OperatingMode = OperatingMode.SHADOW,
    ) -> Iterator[SyntheticRecord]:
        if count < 1:
            raise ValueError("count must be positive")
        start = start_at or datetime(2025, 8, 1, tzinfo=UTC)
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError("start_at must be timezone-aware")

        for index in range(count):
            yield self._one(index=index, start=start, mode=mode)

    def write_jsonl(
        self,
        path: str | Path,
        *,
        count: int,
        start_at: datetime | None = None,
        mode: OperatingMode = OperatingMode.SHADOW,
    ) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8") as handle:
            for record in self.generate(count, start_at=start_at, mode=mode):
                handle.write(json.dumps(record.model_dump(mode="json"), sort_keys=True))
                handle.write("\n")
        return destination

    def _one(
        self, *, index: int, start: datetime, mode: OperatingMode
    ) -> SyntheticRecord:
        # Spread records across twelve months while preserving deterministic ordering.
        day_offset = self.random.randrange(0, 365)
        minute_offset = self.random.randrange(0, 24 * 60)
        evaluation_time = start + timedelta(days=day_offset, minutes=minute_offset)
        month = evaluation_time.month
        seasonal_peak = month in {11, 12}
        weekend = evaluation_time.weekday() >= 5

        current_location = self.random.choice(self.fulfilment_centres)
        alternative_pool = tuple(
            location
            for location in (*self.fulfilment_centres, *self.stores)
            if location != current_location
        )
        alternative_available = self.random.random() < (0.79 if not seasonal_peak else 0.67)
        alternative_location = (
            self.random.choice(alternative_pool) if alternative_available else None
        )

        carrier_service = self.random.choice(tuple(self.carriers))
        carrier_base = self.carriers[carrier_service]
        congestion = (0.12 if seasonal_peak else 0.03) + (0.03 if weekend else 0.0)
        carrier_probability = _clip(
            carrier_base - congestion + self.random.gauss(0.0, 0.035)
        )

        inventory_confidence = _clip(
            self.random.betavariate(18, 2) - (0.08 if seasonal_peak else 0.0),
            0.35,
            0.999,
        )
        inventory_reserved = self.random.random() < 0.96
        unavailable_probability = 0.025 + (1.0 - inventory_confidence) * 0.55
        if seasonal_peak:
            unavailable_probability += 0.045
        inventory_available = self.random.random() >= unavailable_probability

        expected_scan_delay = self.random.expovariate(1 / (0.65 if not weekend else 1.1))
        if self.random.random() < congestion:
            expected_scan_delay += self.random.uniform(1.5, 8.0)
        hours_since_scan = round(min(expected_scan_delay, 24.0), 2)

        promise_hours = self.random.choice((12, 18, 24, 36, 48, 72))
        promised_at = evaluation_time + timedelta(hours=promise_hours)

        gross_margin = _money(self.random.lognormvariate(math.log(48), 0.55))
        cancellation_cost = _money(max(4.0, float(gross_margin) * self.random.uniform(0.2, 0.55)))
        support_cost = _money(self.random.uniform(4.0, 16.0))
        reroute_cost = _money(self.random.uniform(5.0, 21.0))
        carrier_upgrade_cost = _money(self.random.uniform(7.0, 28.0))
        split_cost = _money(self.random.uniform(12.0, 38.0))

        no_action_failure = 1.0 - carrier_probability
        if inventory_reserved and not inventory_available:
            no_action_failure += 0.48
        no_action_failure += max(0.0, 0.78 - inventory_confidence) * 0.55
        no_action_failure += min(0.25, hours_since_scan / 40.0)
        if promise_hours <= 18:
            no_action_failure += 0.09
        no_action_failure = _clip(no_action_failure)
        no_action_on_time = _clip(1.0 - no_action_failure)

        reroute_on_time = (
            _clip(
                0.91
                - (0.09 if seasonal_peak else 0.0)
                - (0.04 if promise_hours <= 12 else 0.0)
                + self.random.gauss(0, 0.025)
            )
            if alternative_available
            else 0.0
        )
        carrier_upgrade_on_time = _clip(
            carrier_probability
            + 0.11
            - (0.05 if inventory_reserved and not inventory_available else 0.0)
            + self.random.gauss(0, 0.02)
        )
        split_possible = alternative_available and self.random.random() < 0.72
        split_on_time = (
            _clip(max(reroute_on_time, carrier_upgrade_on_time) + 0.025)
            if split_possible
            else 0.0
        )

        order_id = f"order-{index + 1:07d}"
        event_id = f"evt-{index + 1:07d}"
        sku = f"SKU-{self.random.randrange(1, 5001):05d}"
        customer_segment = self.random.choices(
            ("STANDARD", "LOYAL", "VIP"), weights=(0.72, 0.23, 0.05), k=1
        )[0]
        freshness = self.random.choices(
            (1, 3, 5, 12, 20, 45), weights=(0.2, 0.27, 0.24, 0.16, 0.09, 0.04), k=1
        )[0]

        refs = (
            SourceReference(
                system="oms", record_id=order_id, observed_at=evaluation_time
            ),
            SourceReference(
                system="wms",
                record_id=f"inventory:{sku}:{current_location}",
                observed_at=evaluation_time - timedelta(minutes=freshness),
            ),
            SourceReference(
                system="carrier",
                record_id=f"shipment:{order_id}",
                observed_at=evaluation_time - timedelta(minutes=min(freshness, 15)),
            ),
        )
        event = OperationalEvent(
            source_system="simulator",
            event_id=event_id,
            event_version=1,
            event_type="ORDER_RISK_EVALUATION_REQUESTED",
            event_time=evaluation_time - timedelta(seconds=10),
            ingestion_time=evaluation_time - timedelta(seconds=2),
            schema_version="v1",
            deduplication_key=f"simulator:{event_id}:v1",
        )
        order = OrderContext(
            order_id=order_id,
            evaluation_time=evaluation_time,
            promised_delivery_at=promised_at,
            gross_margin=gross_margin,
            cancellation_cost=cancellation_cost,
            support_cost=support_cost,
            inventory_reserved=inventory_reserved,
            inventory_available=inventory_available,
            inventory_confidence=inventory_confidence,
            carrier_on_time_probability=carrier_probability,
            hours_since_expected_scan=hours_since_scan,
            alternative_location_available=alternative_available,
            reroute_on_time_probability=reroute_on_time,
            carrier_upgrade_on_time_probability=carrier_upgrade_on_time,
            reroute_cost=reroute_cost,
            carrier_upgrade_cost=carrier_upgrade_cost,
            data_freshness_minutes=freshness,
            source_references=refs,
            customer_id=f"customer-{self.random.randrange(1, 25001):05d}",
            customer_segment=customer_segment,
            sku=sku,
            quantity=self.random.choices((1, 2, 3, 4), weights=(0.76, 0.16, 0.06, 0.02), k=1)[0],
            current_fulfilment_location=current_location,
            alternative_location_id=alternative_location,
            current_carrier_service=carrier_service,
            upgraded_carrier_service=carrier_service.replace("STANDARD", "EXPRESS"),
            split_shipment_possible=split_possible,
            split_shipment_on_time_probability=split_on_time,
            split_shipment_cost=split_cost,
            restricted_product=self.random.random() < 0.012,
        )
        ground_truth = SyntheticGroundTruth(
            no_action_on_time_probability=no_action_on_time,
            reroute_on_time_probability=reroute_on_time,
            carrier_upgrade_on_time_probability=carrier_upgrade_on_time,
            split_shipment_on_time_probability=split_on_time,
            sampled_no_action_failure=self.random.random() > no_action_on_time,
            optimal_action=self._optimal_action(
                order=order,
                probabilities={
                    RecoveryAction.TAKE_NO_ACTION: no_action_on_time,
                    RecoveryAction.REROUTE: reroute_on_time,
                    RecoveryAction.CARRIER_UPGRADE: carrier_upgrade_on_time,
                    RecoveryAction.SPLIT_SHIPMENT: split_on_time,
                },
            ),
        )
        return SyntheticRecord(
            request=EvaluationRequest(event=event, order=order, mode=mode),
            ground_truth=ground_truth,
        )

    @staticmethod
    def _optimal_action(
        *, order: OrderContext, probabilities: dict[RecoveryAction, float]
    ) -> RecoveryAction:
        costs = {
            RecoveryAction.TAKE_NO_ACTION: Decimal("0"),
            RecoveryAction.REROUTE: order.reroute_cost,
            RecoveryAction.CARRIER_UPGRADE: order.carrier_upgrade_cost,
            RecoveryAction.SPLIT_SHIPMENT: order.split_shipment_cost,
        }
        feasible = {
            RecoveryAction.TAKE_NO_ACTION: True,
            RecoveryAction.REROUTE: order.alternative_location_available,
            RecoveryAction.CARRIER_UPGRADE: True,
            RecoveryAction.SPLIT_SHIPMENT: order.split_shipment_possible,
        }
        failure_cost = order.cancellation_cost + order.support_cost
        values: dict[RecoveryAction, Decimal] = {}
        for action, probability in probabilities.items():
            if not feasible[action]:
                continue
            success = Decimal(str(probability))
            values[action] = _money(
                order.gross_margin * success
                - failure_cost * (Decimal("1") - success)
                - costs[action]
            )
        return max(values, key=lambda action: (values[action], action.value))
