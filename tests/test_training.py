from __future__ import annotations

import json

import pytest

from promiseguard.synthetic import SyntheticDataGenerator
from promiseguard.trained_risk import TrainedRiskScorer
from promiseguard.training import train_risk_models


def test_temporal_training_produces_versioned_calibrated_artifact(tmp_path) -> None:
    records = list(SyntheticDataGenerator(seed=42).generate(360))

    summary = train_risk_models(
        records,
        output_dir=tmp_path,
        include_lightgbm=False,
    )
    metrics = json.loads(summary.metrics_path.read_text(encoding="utf-8"))
    scorer = TrainedRiskScorer(summary.artifact_path)
    assessment = scorer.score(records[-1].request.order)

    assert summary.selected_model == "calibrated_logistic"
    assert summary.artifact_path.exists()
    assert metrics["model_version"] == summary.model_version
    assert 0 <= assessment.failure_probability <= 1
    assert assessment.model_version == summary.model_version


def test_training_requires_enough_temporal_evidence(tmp_path) -> None:
    records = list(SyntheticDataGenerator(seed=1).generate(50))

    with pytest.raises(ValueError):
        train_risk_models(records, output_dir=tmp_path, include_lightgbm=False)
