"""Deterministic risk scorer for the first vertical slice.

This is intentionally not presented as a trained ML model. It provides a transparent,
replayable baseline that allows the closed loop to be built and tested before model
training is introduced.
"""

from __future__ import annotations

from promiseguard.models import OrderContext, RiskAssessment, RiskFactor


class DeterministicRiskScorer:
    """Calculate a bounded promise-failure probability from operational signals."""

    model_version = "rules-baseline-v1"

    def score(self, order: OrderContext) -> RiskAssessment:
        probability = 1.0 - order.carrier_on_time_probability
        factors: list[RiskFactor] = [
            RiskFactor(
                code="CARRIER_BASELINE",
                contribution=round(probability, 4),
                explanation="Carrier baseline implies residual promise-failure risk.",
            )
        ]

        if order.inventory_reserved and not order.inventory_available:
            probability += 0.45
            factors.append(
                RiskFactor(
                    code="RESERVED_STOCK_UNAVAILABLE",
                    contribution=0.45,
                    explanation="Reserved inventory is not available at the selected location.",
                )
            )

        if order.inventory_confidence < 0.80:
            contribution = min(0.18, (0.80 - order.inventory_confidence) * 0.60)
            probability += contribution
            factors.append(
                RiskFactor(
                    code="LOW_INVENTORY_CONFIDENCE",
                    contribution=round(contribution, 4),
                    explanation="Inventory confidence is below the operational threshold.",
                )
            )

        if order.hours_since_expected_scan >= 2.0:
            contribution = min(0.25, order.hours_since_expected_scan / 48.0)
            probability += contribution
            factors.append(
                RiskFactor(
                    code="MISSING_CARRIER_SCAN",
                    contribution=round(contribution, 4),
                    explanation="The expected carrier scan has not arrived on time.",
                )
            )

        hours_to_promise = (
            order.promised_delivery_at - order.evaluation_time
        ).total_seconds() / 3_600
        if hours_to_promise <= 24.0:
            probability += 0.08
            factors.append(
                RiskFactor(
                    code="PROMISE_WINDOW_TIGHT",
                    contribution=0.08,
                    explanation="Less than 24 hours remain before the customer promise date.",
                )
            )

        warnings: list[str] = []
        confidence = min(order.inventory_confidence, 0.98)
        if order.data_freshness_minutes > 15:
            warnings.append("STALE_OPERATIONAL_CONTEXT")
            confidence = min(confidence, 0.45)
        if not order.source_references:
            warnings.append("MISSING_SOURCE_REFERENCES")
            confidence = 0.0

        return RiskAssessment(
            failure_probability=round(min(max(probability, 0.01), 0.99), 4),
            confidence=round(min(max(confidence, 0.0), 1.0), 4),
            model_version=self.model_version,
            feature_timestamp=order.evaluation_time,
            factors=tuple(factors),
            data_quality_warnings=tuple(warnings),
            evidence_references=order.source_references,
        )
