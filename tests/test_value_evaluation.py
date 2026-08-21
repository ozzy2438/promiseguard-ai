from __future__ import annotations

from promiseguard.synthetic import SyntheticDataGenerator
from promiseguard.value_evaluation import SyntheticValueEvaluator


def test_value_evaluation_is_reproducible_and_truthfully_labelled() -> None:
    first_records = list(SyntheticDataGenerator(seed=77).generate(500))
    second_records = list(SyntheticDataGenerator(seed=77).generate(500))

    first = SyntheticValueEvaluator().evaluate(first_records)
    second = SyntheticValueEvaluator().evaluate(second_records)

    assert first == second
    assert first.records == 500
    assert 0 <= first.intervention_rate <= 1
    assert 0 <= first.action_agreement_with_ground_truth <= 1
    assert 0 <= first.false_intervention_rate <= 1
    assert first.mean_regret >= 0
    assert sum(first.selected_action_counts.values()) == 500
    assert first.to_json_dict()["evidence_classification"] == ("SYNTHETIC_COUNTERFACTUAL_BACKTEST")


def test_value_evaluation_rejects_empty_input() -> None:
    evaluator = SyntheticValueEvaluator()

    try:
        evaluator.evaluate([])
    except ValueError as exc:
        assert "at least one" in str(exc)
    else:
        raise AssertionError("empty evaluation should be rejected")
