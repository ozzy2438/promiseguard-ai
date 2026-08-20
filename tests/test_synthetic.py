from __future__ import annotations

import json

import pytest

from promiseguard.models import SyntheticRecord
from promiseguard.synthetic import SyntheticDataGenerator


def test_synthetic_generation_is_reproducible() -> None:
    first = list(SyntheticDataGenerator(seed=7).generate(5))
    second = list(SyntheticDataGenerator(seed=7).generate(5))
    different = list(SyntheticDataGenerator(seed=8).generate(5))

    assert first == second
    assert first != different
    assert all(record.request.order.currency == "AUD" for record in first)
    assert all(record.ground_truth.optimal_action for record in first)


def test_synthetic_jsonl_round_trip(tmp_path) -> None:
    path = SyntheticDataGenerator(seed=11).write_jsonl(
        tmp_path / "orders.jsonl", count=12
    )
    lines = path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 12
    parsed = [SyntheticRecord.model_validate(json.loads(line)) for line in lines]
    assert parsed[0].request.event.event_id == "evt-0000001"


def test_synthetic_generator_rejects_non_positive_count() -> None:
    with pytest.raises(ValueError):
        list(SyntheticDataGenerator().generate(0))
