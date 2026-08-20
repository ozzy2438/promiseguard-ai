from __future__ import annotations

import json
import sys
from pathlib import Path

from promiseguard import (
    synthetic_cli,
    synthetic_events_cli,
    training_cli,
    value_evaluation_cli,
)


def test_synthetic_and_event_cli_round_trip(
    tmp_path: Path,
    monkeypatch,
) -> None:
    orders = tmp_path / "orders.jsonl"
    events = tmp_path / "events.jsonl"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "promiseguard-generate",
            "--count",
            "150",
            "--seed",
            "123",
            "--output",
            str(orders),
        ],
    )
    synthetic_cli.main()
    assert len(orders.read_text(encoding="utf-8").splitlines()) == 150

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "promiseguard-generate-events",
            "--input",
            str(orders),
            "--output",
            str(events),
            "--seed",
            "123",
            "--duplicate-rate",
            "0.1",
            "--late-arrival-rate",
            "0.1",
            "--out-of-order-rate",
            "0.1",
        ],
    )
    synthetic_events_cli.main()
    assert len(events.read_text(encoding="utf-8").splitlines()) >= 600


def test_training_and_value_evaluation_cli_round_trip(
    tmp_path: Path,
    monkeypatch,
) -> None:
    orders = tmp_path / "orders.jsonl"
    models = tmp_path / "models"
    value_report = tmp_path / "value.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "promiseguard-generate",
            "--count",
            "500",
            "--seed",
            "456",
            "--output",
            str(orders),
        ],
    )
    synthetic_cli.main()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "promiseguard-train",
            "--input",
            str(orders),
            "--output-dir",
            str(models),
            "--no-lightgbm",
        ],
    )
    training_cli.main()
    artifact = models / "risk_model.joblib"
    metrics = models / "risk_model_metrics.json"
    assert artifact.exists()
    assert json.loads(metrics.read_text(encoding="utf-8"))["training_records"] == 500

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "promiseguard-evaluate-value",
            "--input",
            str(orders),
            "--model-path",
            str(artifact),
            "--output",
            str(value_report),
            "--limit",
            "200",
        ],
    )
    value_evaluation_cli.main()
    payload = json.loads(value_report.read_text(encoding="utf-8"))
    assert payload["records"] == 200
    assert payload["evidence_classification"] == "SYNTHETIC_COUNTERFACTUAL_BACKTEST"
