from promiseguard.value_design import (
    ValueClaimBoundary,
    ValueMeasurementDesign,
    implemented_local_designs,
)


def test_local_value_designs_keep_synthetic_claim_boundary() -> None:
    implemented = implemented_local_designs()
    designs = {spec.design for spec in implemented}
    assert ValueMeasurementDesign.SYNTHETIC_COUNTERFACTUAL_BACKTEST in designs
    assert ValueMeasurementDesign.NO_ACTION_BASELINE in designs
    assert ValueMeasurementDesign.SHADOW_MODE_COUNTERFACTUAL in designs
    assert ValueMeasurementDesign.CONTROL_GROUP not in designs
    for spec in implemented:
        if spec.design is ValueMeasurementDesign.SYNTHETIC_COUNTERFACTUAL_BACKTEST:
            assert spec.claim_boundary is ValueClaimBoundary.SYNTHETIC_ONLY
