"""Offline business-value evaluation against synthetic counterfactual ground truth."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal
from math import ceil
from typing import Any

from promiseguard.models import OrderContext, RecoveryAction, SyntheticRecord
from promiseguard.optimizer import DecisionOptimizer
from promiseguard.risk import BatchRiskScorer, DeterministicRiskScorer, RiskScorer
from promiseguard.simulator import RecoverySimulator

_CENTS = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class ValueEvaluationSummary:
    """Aggregate shadow-mode value evidence with explicit synthetic semantics."""

    records: int
    model_version: str
    simulator_version: str
    optimiser_version: str
    intervention_rate: float
    action_agreement_with_ground_truth: float
    false_intervention_rate: float
    mean_on_time_probability_uplift: float
    simulated_incremental_value: Decimal
    simulated_intervention_cost: Decimal
    simulated_gross_uplift_before_intervention_cost: Decimal
    mean_regret: Decimal
    p95_regret: Decimal
    selected_action_counts: dict[str, int]

    def to_json_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "simulated_incremental_value",
            "simulated_intervention_cost",
            "simulated_gross_uplift_before_intervention_cost",
            "mean_regret",
            "p95_regret",
        ):
            payload[key] = str(payload[key])
        payload["evidence_classification"] = "SYNTHETIC_COUNTERFACTUAL_BACKTEST"
        payload["claim_limit"] = (
            "This report is not production revenue and must not be represented as such."
        )
        return payload


class SyntheticValueEvaluator:
    """Measure decision value against known outcomes without causal overclaiming."""

    def __init__(
        self,
        *,
        scorer: RiskScorer | None = None,
        simulator: RecoverySimulator | None = None,
        optimiser: DecisionOptimizer | None = None,
    ) -> None:
        self.scorer = scorer or DeterministicRiskScorer()
        self.simulator = simulator or RecoverySimulator()
        self.optimiser = optimiser or DecisionOptimizer()

    def evaluate(self, records: Iterable[SyntheticRecord]) -> ValueEvaluationSummary:
        selected_counts: Counter[str] = Counter()
        regrets: list[Decimal] = []
        incremental_values: list[Decimal] = []
        intervention_costs: list[Decimal] = []
        probability_uplifts: list[float] = []
        record_count = 0
        interventions = 0
        false_interventions = 0
        correct_actions = 0

        for batch in self._batches(records, size=2_048):
            orders = tuple(record.request.order for record in batch)
            if isinstance(self.scorer, BatchRiskScorer):
                risks = self.scorer.score_many(orders)
            else:
                risks = tuple(self.scorer.score(order) for order in orders)

            for record, risk in zip(batch, risks, strict=True):
                record_count += 1
                options = self.simulator.simulate(record.request.order, risk)
                recommendation = self.optimiser.select(options)
                selected = recommendation.selected_action
                selected_counts[selected.value] += 1
                correct_actions += int(selected is record.ground_truth.optimal_action)

                selected_value = self._ground_truth_value(record, selected)
                no_action_value = self._ground_truth_value(
                    record,
                    RecoveryAction.TAKE_NO_ACTION,
                )
                optimal_value = self._ground_truth_value(
                    record,
                    record.ground_truth.optimal_action,
                )
                incremental = _money(selected_value - no_action_value)
                regret = _money(optimal_value - selected_value)
                cost = self._action_cost(record.request.order, selected)
                selected_probability = self._ground_truth_probability(record, selected)
                no_action_probability = (
                    record.ground_truth.no_action_on_time_probability
                )

                incremental_values.append(incremental)
                regrets.append(max(Decimal("0"), regret))
                intervention_costs.append(cost)
                probability_uplifts.append(
                    selected_probability - no_action_probability
                )

                if selected is not RecoveryAction.TAKE_NO_ACTION:
                    interventions += 1
                    false_interventions += int(incremental <= 0)

        if record_count == 0:
            raise ValueError("at least one synthetic record is required")

        sorted_regrets = sorted(regrets)
        p95_index = max(
            0,
            min(len(sorted_regrets) - 1, ceil(len(sorted_regrets) * 0.95) - 1),
        )
        total_incremental = _money(sum(incremental_values, Decimal("0")))
        total_cost = _money(sum(intervention_costs, Decimal("0")))
        gross_uplift = _money(total_incremental + total_cost)

        return ValueEvaluationSummary(
            records=record_count,
            model_version=self.scorer.model_version,
            simulator_version=self.simulator.simulator_version,
            optimiser_version=self.optimiser.optimiser_version,
            intervention_rate=interventions / record_count,
            action_agreement_with_ground_truth=correct_actions / record_count,
            false_intervention_rate=(
                false_interventions / interventions if interventions else 0.0
            ),
            mean_on_time_probability_uplift=sum(probability_uplifts) / record_count,
            simulated_incremental_value=total_incremental,
            simulated_intervention_cost=total_cost,
            simulated_gross_uplift_before_intervention_cost=gross_uplift,
            mean_regret=_money(sum(regrets, Decimal("0")) / Decimal(record_count)),
            p95_regret=sorted_regrets[p95_index],
            selected_action_counts=dict(sorted(selected_counts.items())),
        )

    @staticmethod
    def _batches(
        records: Iterable[SyntheticRecord],
        *,
        size: int,
    ) -> Iterator[Sequence[SyntheticRecord]]:
        batch: list[SyntheticRecord] = []
        for record in records:
            batch.append(record)
            if len(batch) >= size:
                yield tuple(batch)
                batch.clear()
        if batch:
            yield tuple(batch)

    @classmethod
    def _ground_truth_value(
        cls,
        record: SyntheticRecord,
        action: RecoveryAction,
    ) -> Decimal:
        probability = Decimal(str(cls._ground_truth_probability(record, action)))
        order = record.request.order
        failure_cost = order.cancellation_cost + order.support_cost
        return _money(
            order.gross_margin * probability
            - failure_cost * (Decimal("1") - probability)
            - cls._action_cost(order, action)
        )

    @staticmethod
    def _ground_truth_probability(
        record: SyntheticRecord,
        action: RecoveryAction,
    ) -> float:
        probabilities = {
            RecoveryAction.TAKE_NO_ACTION: (
                record.ground_truth.no_action_on_time_probability
            ),
            RecoveryAction.REROUTE: record.ground_truth.reroute_on_time_probability,
            RecoveryAction.CARRIER_UPGRADE: (
                record.ground_truth.carrier_upgrade_on_time_probability
            ),
            RecoveryAction.SPLIT_SHIPMENT: (
                record.ground_truth.split_shipment_on_time_probability
            ),
        }
        if action not in probabilities:
            raise ValueError(f"action {action.value} has no synthetic ground truth")
        return probabilities[action]

    @staticmethod
    def _action_cost(order: OrderContext, action: RecoveryAction) -> Decimal:
        return {
            RecoveryAction.TAKE_NO_ACTION: Decimal("0"),
            RecoveryAction.REROUTE: order.reroute_cost,
            RecoveryAction.CARRIER_UPGRADE: order.carrier_upgrade_cost,
            RecoveryAction.SPLIT_SHIPMENT: order.split_shipment_cost,
        }.get(action, Decimal("0"))
