"""Generate reproducible operational event streams with reliability anomalies."""

from __future__ import annotations

import random
from collections.abc import Iterable, Iterator
from datetime import timedelta

from promiseguard.models import (
    OperationalEvent,
    SyntheticEventAnomaly,
    SyntheticEventEnvelope,
    SyntheticRecord,
)


class SyntheticEventStreamGenerator:
    """Expand order snapshots into event streams with known anomaly labels."""

    def __init__(self, *, seed: int = 20260820) -> None:
        self.random = random.Random(seed)

    def generate(
        self,
        records: Iterable[SyntheticRecord],
        *,
        duplicate_rate: float = 0.01,
        late_arrival_rate: float = 0.02,
        out_of_order_rate: float = 0.02,
    ) -> Iterator[SyntheticEventEnvelope]:
        for rate in (duplicate_rate, late_arrival_rate, out_of_order_rate):
            if not 0.0 <= rate <= 1.0:
                raise ValueError("anomaly rates must be between zero and one")

        for record in records:
            envelopes = self._order_events(
                record,
                late_arrival=self.random.random() < late_arrival_rate,
            )
            if self.random.random() < out_of_order_rate:
                envelopes[1], envelopes[2] = envelopes[2], envelopes[1]
                envelopes = [
                    envelope.model_copy(
                        update={
                            "emission_sequence": index,
                            "anomaly": (
                                SyntheticEventAnomaly.OUT_OF_ORDER
                                if envelope.event_sequence == 3
                                else envelope.anomaly
                            ),
                        }
                    )
                    for index, envelope in enumerate(envelopes, start=1)
                ]

            yield from envelopes

            if self.random.random() < duplicate_rate:
                original = self.random.choice(envelopes)
                yield original.model_copy(
                    update={
                        "emission_sequence": len(envelopes) + 1,
                        "anomaly": SyntheticEventAnomaly.DUPLICATE,
                        "duplicate_of": original.event.event_id,
                    }
                )

    @staticmethod
    def _order_events(
        record: SyntheticRecord,
        *,
        late_arrival: bool,
    ) -> list[SyntheticEventEnvelope]:
        order = record.request.order
        base = order.evaluation_time
        definitions = (
            (
                1,
                "ORDER_CREATED",
                base - timedelta(hours=6),
                base - timedelta(hours=6) + timedelta(seconds=2),
                {"customer_id": order.customer_id, "sku": order.sku},
            ),
            (
                2,
                "INVENTORY_RESERVATION_RECORDED",
                base - timedelta(hours=2),
                (
                    base - timedelta(minutes=30)
                    if late_arrival
                    else base - timedelta(hours=2) + timedelta(seconds=5)
                ),
                {
                    "location": order.current_fulfilment_location,
                    "inventory_available": order.inventory_available,
                    "inventory_confidence": order.inventory_confidence,
                },
            ),
            (
                3,
                "CARRIER_STATUS_OBSERVED",
                base - timedelta(hours=1),
                base - timedelta(hours=1) + timedelta(seconds=4),
                {
                    "service": order.current_carrier_service,
                    "hours_since_expected_scan": order.hours_since_expected_scan,
                },
            ),
            (
                4,
                "ORDER_RISK_EVALUATION_REQUESTED",
                record.request.event.event_time,
                record.request.event.ingestion_time,
                {"promised_delivery_at": order.promised_delivery_at.isoformat()},
            ),
        )
        envelopes: list[SyntheticEventEnvelope] = []
        for sequence, event_type, event_time, ingestion_time, payload in definitions:
            event_id = f"{order.order_id}:{event_type.lower()}"
            anomaly = (
                SyntheticEventAnomaly.LATE_ARRIVAL
                if late_arrival and sequence == 2
                else SyntheticEventAnomaly.NONE
            )
            envelopes.append(
                SyntheticEventEnvelope(
                    order_id=order.order_id,
                    event_sequence=sequence,
                    emission_sequence=sequence,
                    event=OperationalEvent(
                        source_system="synthetic-event-stream",
                        event_id=event_id,
                        event_version=1,
                        event_type=event_type,
                        event_time=event_time,
                        ingestion_time=ingestion_time,
                        schema_version="v1",
                        deduplication_key=f"synthetic-event-stream:{event_id}:v1",
                    ),
                    payload=payload,
                    anomaly=anomaly,
                )
            )
        return envelopes
