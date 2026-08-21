"""Inference adapter for calibrated risk-model artifacts."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any
from warnings import catch_warnings, filterwarnings

import joblib
import numpy as np

from promiseguard.features import FEATURE_NAMES, extract_features
from promiseguard.models import OrderContext, RiskAssessment, RiskFactor


class TrainedRiskScorer:
    """Load a versioned sklearn-compatible artifact and score active orders."""

    def __init__(self, artifact_path: str | Path) -> None:
        artifact: dict[str, Any] = joblib.load(artifact_path)
        if tuple(artifact["feature_names"]) != FEATURE_NAMES:
            raise ValueError("risk artifact feature schema does not match runtime schema")
        self.estimator = artifact["estimator"]
        self.model_version = str(artifact["model_version"])

    def score(self, order: OrderContext) -> RiskAssessment:
        return self.score_many((order,))[0]

    def score_many(self, orders: Sequence[OrderContext]) -> tuple[RiskAssessment, ...]:
        if not orders:
            return ()
        values = np.asarray([extract_features(order) for order in orders], dtype=float)
        with catch_warnings():
            filterwarnings(
                "ignore",
                message="X does not have valid feature names.*",
                category=UserWarning,
            )
            probabilities = self.estimator.predict_proba(values)[:, 1]
        return tuple(
            self._assessment(order, float(probability))
            for order, probability in zip(orders, probabilities, strict=True)
        )

    def _assessment(self, order: OrderContext, probability: float) -> RiskAssessment:
        warnings: list[str] = []
        confidence = min(order.inventory_confidence, 0.98)
        if order.data_freshness_minutes > 15:
            warnings.append("STALE_OPERATIONAL_CONTEXT")
            confidence = min(confidence, 0.45)

        return RiskAssessment(
            failure_probability=round(min(max(probability, 0.01), 0.99), 4),
            confidence=round(confidence, 4),
            model_version=self.model_version,
            feature_timestamp=order.evaluation_time,
            factors=self._operational_factors(order),
            data_quality_warnings=tuple(warnings),
            evidence_references=order.source_references,
        )

    @staticmethod
    def _operational_factors(order: OrderContext) -> tuple[RiskFactor, ...]:
        factors = [
            RiskFactor(
                code="CARRIER_BASELINE",
                contribution=round(1.0 - order.carrier_on_time_probability, 4),
                explanation="Carrier reliability is an input to the calibrated model.",
            )
        ]
        if order.inventory_reserved and not order.inventory_available:
            factors.append(
                RiskFactor(
                    code="RESERVED_STOCK_UNAVAILABLE",
                    contribution=1.0,
                    explanation="Reserved stock is unavailable in the current context.",
                )
            )
        if order.hours_since_expected_scan >= 2.0:
            factors.append(
                RiskFactor(
                    code="MISSING_CARRIER_SCAN",
                    contribution=round(order.hours_since_expected_scan, 4),
                    explanation="The expected carrier scan is delayed.",
                )
            )
        return tuple(factors)
