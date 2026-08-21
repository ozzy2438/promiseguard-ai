"""Incremental value measurement designs and claim boundaries.

The local V1 evaluator implements a synthetic counterfactual backtest. Other
designs are first-class types so shadow, approval and future pilot evidence
cannot be silently relabelled as proven causal revenue.
"""

from __future__ import annotations

from enum import StrEnum

from promiseguard.models import StrictModel


class ValueMeasurementDesign(StrEnum):
    SYNTHETIC_COUNTERFACTUAL_BACKTEST = "SYNTHETIC_COUNTERFACTUAL_BACKTEST"
    NO_ACTION_BASELINE = "NO_ACTION_BASELINE"
    SHADOW_MODE_COUNTERFACTUAL = "SHADOW_MODE_COUNTERFACTUAL"
    CONTROL_GROUP = "CONTROL_GROUP"
    MATCHED_COMPARISON_GROUP = "MATCHED_COMPARISON_GROUP"
    QUASI_EXPERIMENTAL = "QUASI_EXPERIMENTAL"


class ValueClaimBoundary(StrEnum):
    SYNTHETIC_ONLY = "SYNTHETIC_ONLY"
    OPERATIONAL_OBSERVED_NOT_CAUSAL = "OPERATIONAL_OBSERVED_NOT_CAUSAL"
    CAUSAL_REQUIRES_DESIGNED_EXPERIMENT = "CAUSAL_REQUIRES_DESIGNED_EXPERIMENT"


class ValueMetric(StrEnum):
    AVOIDED_PROMISE_FAILURES = "AVOIDED_PROMISE_FAILURES"
    RECOVERED_ORDERS = "RECOVERED_ORDERS"
    INCREMENTAL_RECOVERED_MARGIN = "INCREMENTAL_RECOVERED_MARGIN"
    INCREMENTAL_INTERVENTION_COST = "INCREMENTAL_INTERVENTION_COST"
    NET_VALUE = "NET_VALUE"
    FALSE_POSITIVE_INTERVENTION_COST = "FALSE_POSITIVE_INTERVENTION_COST"
    APPROVAL_RATE = "APPROVAL_RATE"
    EXECUTION_SUCCESS_RATE = "EXECUTION_SUCCESS_RATE"
    INTERVENTION_EFFECTIVENESS = "INTERVENTION_EFFECTIVENESS"
    CALIBRATION = "CALIBRATION"
    OPERATIONAL_LATENCY = "OPERATIONAL_LATENCY"


class ValueDesignSpec(StrictModel):
    design: ValueMeasurementDesign
    implemented_locally: bool
    requires_operational_users: bool
    requires_live_outcomes: bool
    claim_boundary: ValueClaimBoundary
    comparison_mechanism: str
    notes: str


LOCAL_VALUE_DESIGNS: tuple[ValueDesignSpec, ...] = (
    ValueDesignSpec(
        design=ValueMeasurementDesign.SYNTHETIC_COUNTERFACTUAL_BACKTEST,
        implemented_locally=True,
        requires_operational_users=False,
        requires_live_outcomes=False,
        claim_boundary=ValueClaimBoundary.SYNTHETIC_ONLY,
        comparison_mechanism="known synthetic outcomes vs explicit TAKE_NO_ACTION baseline",
        notes="Machine-readable 100k-order backtest. Not real company revenue.",
    ),
    ValueDesignSpec(
        design=ValueMeasurementDesign.NO_ACTION_BASELINE,
        implemented_locally=True,
        requires_operational_users=False,
        requires_live_outcomes=False,
        claim_boundary=ValueClaimBoundary.SYNTHETIC_ONLY,
        comparison_mechanism="every candidate action ranked against TAKE_NO_ACTION",
        notes="Deterministic optimiser never omits the no-action option.",
    ),
    ValueDesignSpec(
        design=ValueMeasurementDesign.SHADOW_MODE_COUNTERFACTUAL,
        implemented_locally=True,
        requires_operational_users=True,
        requires_live_outcomes=True,
        claim_boundary=ValueClaimBoundary.OPERATIONAL_OBSERVED_NOT_CAUSAL,
        comparison_mechanism="shadow decision vs later observed outcome without execution",
        notes="Local APIs support SHADOW mode. Causal claims still require a designed pilot.",
    ),
    ValueDesignSpec(
        design=ValueMeasurementDesign.CONTROL_GROUP,
        implemented_locally=False,
        requires_operational_users=True,
        requires_live_outcomes=True,
        claim_boundary=ValueClaimBoundary.CAUSAL_REQUIRES_DESIGNED_EXPERIMENT,
        comparison_mechanism="randomised or holdout control that does not receive interventions",
        notes="Requires operational assignment policy during UAT/pilot. Not claimed locally.",
    ),
    ValueDesignSpec(
        design=ValueMeasurementDesign.MATCHED_COMPARISON_GROUP,
        implemented_locally=False,
        requires_operational_users=True,
        requires_live_outcomes=True,
        claim_boundary=ValueClaimBoundary.CAUSAL_REQUIRES_DESIGNED_EXPERIMENT,
        comparison_mechanism="matched unexecuted orders with similar risk and economics",
        notes="Feasible after live OMS outcomes exist. Matching spec is documented, not run.",
    ),
    ValueDesignSpec(
        design=ValueMeasurementDesign.QUASI_EXPERIMENTAL,
        implemented_locally=False,
        requires_operational_users=True,
        requires_live_outcomes=True,
        claim_boundary=ValueClaimBoundary.CAUSAL_REQUIRES_DESIGNED_EXPERIMENT,
        comparison_mechanism="difference-in-differences or interrupted time series if assigned",
        notes="Only after a real operating window exists. Not inferred from synthetic data.",
    ),
)


def implemented_local_designs() -> tuple[ValueDesignSpec, ...]:
    return tuple(spec for spec in LOCAL_VALUE_DESIGNS if spec.implemented_locally)
