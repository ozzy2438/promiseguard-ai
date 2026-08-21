# Synthetic counterfactual value evaluation

## Purpose

Measure whether the decision engine selects economically useful recovery actions when the
synthetic generator provides known outcomes for no action, reroute, carrier upgrade and split
shipment.

## 100,000-order result

| Metric | Result |
|---|---:|
| Action agreement with known optimal action | **95.043%** |
| Intervention rate | 41.513% |
| False-intervention rate | **4.664%** |
| Mean on-time-probability uplift | 11.492 percentage points |
| Mean regret per order | A$0.06 |
| P95 regret | A$0.00 |
| Simulated incremental value, action cost included | **A$646,663.53** |
| Simulated intervention cost | A$509,397.34 |

Action counts:

- `TAKE_NO_ACTION`: 58,487
- `CARRIER_UPGRADE`: 25,264
- `REROUTE`: 11,944
- `SPLIT_SHIPMENT`: 4,305

## Claim boundary

These values are **synthetic counterfactual backtest results**, not revenue earned for a real
company. The committed JSON report explicitly carries the classification
`SYNTHETIC_COUNTERFACTUAL_BACKTEST` and a claim-limit statement.

The primary incremental-value figure already includes intervention cost in each action’s ground-
truth expected value. `simulated_gross_uplift_before_intervention_cost` is included only as a
reconciliation view and must not be added to the primary value figure.

## Reproduce

```bash
promiseguard-generate \
  --count 100000 \
  --seed 20260820 \
  --output data/generated/orders.jsonl

promiseguard-train \
  --input data/generated/orders.jsonl \
  --output-dir artifacts/models

promiseguard-evaluate-value \
  --input data/generated/orders.jsonl \
  --model-path artifacts/models/risk_model.joblib \
  --output artifacts/evidence/value_evaluation.json
```
