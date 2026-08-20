from __future__ import annotations

from promiseguard.models import SyntheticEventAnomaly
from promiseguard.synthetic import SyntheticDataGenerator
from promiseguard.synthetic_events import SyntheticEventStreamGenerator


def test_event_stream_is_reproducible() -> None:
    records = list(SyntheticDataGenerator(seed=10).generate(5))
    first = list(SyntheticEventStreamGenerator(seed=20).generate(records))
    second = list(SyntheticEventStreamGenerator(seed=20).generate(records))

    assert first == second
    assert len(first) >= 20


def test_event_stream_can_force_all_supported_anomalies() -> None:
    records = list(SyntheticDataGenerator(seed=30).generate(3))
    events = list(
        SyntheticEventStreamGenerator(seed=40).generate(
            records,
            duplicate_rate=1.0,
            late_arrival_rate=1.0,
            out_of_order_rate=1.0,
        )
    )
    anomalies = {event.anomaly for event in events}

    assert SyntheticEventAnomaly.DUPLICATE in anomalies
    assert SyntheticEventAnomaly.LATE_ARRIVAL in anomalies
    assert SyntheticEventAnomaly.OUT_OF_ORDER in anomalies
    duplicates = [event for event in events if event.anomaly is SyntheticEventAnomaly.DUPLICATE]
    assert len(duplicates) == 3
    assert all(event.duplicate_of == event.event.event_id for event in duplicates)


def test_event_stream_rejects_invalid_rates() -> None:
    records = list(SyntheticDataGenerator(seed=50).generate(1))

    try:
        list(
            SyntheticEventStreamGenerator().generate(
                records,
                duplicate_rate=1.1,
            )
        )
    except ValueError as exc:
        assert "between zero and one" in str(exc)
    else:
        raise AssertionError("invalid anomaly rate should be rejected")
