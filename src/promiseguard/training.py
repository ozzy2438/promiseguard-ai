"""Temporal model training, calibration and artifact production."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from promiseguard.features import FEATURE_NAMES, extract_features
from promiseguard.models import SyntheticRecord


@dataclass(frozen=True, slots=True)
class TrainedModelSummary:
    artifact_path: Path
    metrics_path: Path
    selected_model: str
    model_version: str
    metrics: dict[str, dict[str, float]]


def expected_calibration_error(
    y_true: np.ndarray, probabilities: np.ndarray, *, bins: int = 10
) -> float:
    boundaries = np.linspace(0.0, 1.0, bins + 1)
    error = 0.0
    for lower, upper in zip(boundaries[:-1], boundaries[1:], strict=True):
        if upper == 1.0:
            mask = (probabilities >= lower) & (probabilities <= upper)
        else:
            mask = (probabilities >= lower) & (probabilities < upper)
        if not np.any(mask):
            continue
        confidence = float(np.mean(probabilities[mask]))
        accuracy = float(np.mean(y_true[mask]))
        error += float(np.mean(mask)) * abs(accuracy - confidence)
    return error


def train_risk_models(
    records: Sequence[SyntheticRecord],
    *,
    output_dir: str | Path,
    random_state: int = 20260820,
    include_lightgbm: bool = True,
) -> TrainedModelSummary:
    if len(records) < 120:
        raise ValueError("at least 120 records are required for temporal training")

    ordered = sorted(records, key=lambda record: record.request.order.evaluation_time)
    x = np.asarray([extract_features(record.request.order) for record in ordered], dtype=float)
    y = np.asarray(
        [int(record.ground_truth.sampled_no_action_failure) for record in ordered],
        dtype=int,
    )
    split_index = max(100, int(len(ordered) * 0.8))
    split_index = min(split_index, len(ordered) - 20)
    x_train, x_test = x[:split_index], x[split_index:]
    y_train, y_test = y[:split_index], y[split_index:]
    if len(np.unique(y_train)) < 2 or len(np.unique(y_test)) < 2:
        raise ValueError("training and temporal holdout must each contain both classes")

    candidates: dict[str, Any] = {
        "calibrated_logistic": CalibratedClassifierCV(
            Pipeline(
                [
                    ("scale", StandardScaler()),
                    (
                        "model",
                        LogisticRegression(
                            max_iter=1_000,
                            class_weight="balanced",
                            random_state=random_state,
                        ),
                    ),
                ]
            ),
            method="sigmoid",
            cv=3,
        )
    }
    if include_lightgbm:
        try:
            from lightgbm import LGBMClassifier
        except ImportError:
            pass
        else:
            candidates["calibrated_lightgbm"] = CalibratedClassifierCV(
                LGBMClassifier(
                    n_estimators=120,
                    learning_rate=0.04,
                    num_leaves=15,
                    min_child_samples=25,
                    subsample=0.9,
                    colsample_bytree=0.9,
                    class_weight="balanced",
                    random_state=random_state,
                    verbosity=-1,
                ),
                method="sigmoid",
                cv=3,
            )

    metrics: dict[str, dict[str, float]] = {}
    trained: dict[str, Any] = {}
    for name, estimator in candidates.items():
        estimator.fit(x_train, y_train)
        probabilities = estimator.predict_proba(x_test)[:, 1]
        trained[name] = estimator
        metrics[name] = {
            "pr_auc": float(average_precision_score(y_test, probabilities)),
            "roc_auc": float(roc_auc_score(y_test, probabilities)),
            "brier_score": float(brier_score_loss(y_test, probabilities)),
            "expected_calibration_error": expected_calibration_error(
                y_test, probabilities
            ),
            "holdout_prevalence": float(np.mean(y_test)),
            "holdout_size": float(len(y_test)),
        }

    selected_name = min(
        metrics,
        key=lambda name: (
            metrics[name]["brier_score"],
            -metrics[name]["pr_auc"],
        ),
    )
    selected = trained[selected_name]
    version_material = json.dumps(
        {
            "selected": selected_name,
            "features": FEATURE_NAMES,
            "metrics": metrics[selected_name],
            "records": len(records),
            "random_state": random_state,
        },
        sort_keys=True,
    )
    version = f"risk-{selected_name}-{sha256(version_material.encode()).hexdigest()[:12]}"
    artifact = {
        "estimator": selected,
        "feature_names": FEATURE_NAMES,
        "model_version": version,
        "trained_at": datetime.now(UTC).isoformat(),
        "training_records": len(records),
        "temporal_holdout_records": len(y_test),
        "metrics": metrics[selected_name],
    }

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    artifact_path = destination / "risk_model.joblib"
    metrics_path = destination / "risk_model_metrics.json"
    joblib.dump(artifact, artifact_path)
    metrics_payload = {
        "selected_model": selected_name,
        "model_version": version,
        "all_candidates": metrics,
        "feature_names": FEATURE_NAMES,
        "training_records": len(records),
        "temporal_holdout_records": len(y_test),
    }
    metrics_path.write_text(
        json.dumps(metrics_payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return TrainedModelSummary(
        artifact_path=artifact_path,
        metrics_path=metrics_path,
        selected_model=selected_name,
        model_version=version,
        metrics=metrics,
    )
