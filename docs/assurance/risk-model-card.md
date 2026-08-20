# Promise-risk model card — 100,000-order synthetic temporal backtest

## Intended use

Estimate the probability that an active order will miss its promised delivery date. The model is
an input to deterministic recovery simulation and policy; it is not authorised to execute actions,
calculate financial values or override data-quality controls.

## Data classification

- **Synthetic only** — no real customers or production transactions.
- 100,000 reproducible orders generated with seed `20260820`.
- Twelve-month temporal history with a final 20% temporal holdout.
- Dataset hash and generation metadata are recorded in
  `evidence/synthetic-dataset-100k-manifest.json`.

## Candidates and selection

The selection rule minimises Brier score, then maximises PR-AUC as a tie-breaker.

| Candidate | PR-AUC | ROC-AUC | Brier | ECE |
|---|---:|---:|---:|---:|
| Calibrated logistic | 0.4280 | 0.6790 | 0.1512 | 0.0075 |
| Calibrated LightGBM | **0.4387** | **0.6911** | **0.1500** | 0.0122 |

Selected artifact: `risk-calibrated-lightgbm-3814942c3b36`.

The holdout failure prevalence was 0.21685. PR-AUC is therefore materially above the no-skill
prevalence baseline, but ranking performance remains moderate rather than exceptional. The model
must not be represented as production-proven.

## Required runtime controls

- Point-in-time feature extraction only.
- Explicit model and feature-schema version checks.
- Confidence downgrade and policy block for stale operational context.
- Segment-level monitoring before any real-world deployment.
- Shadow and approval modes before bounded autonomy.
- Kill switch and automatic action-profile suspension after failed or compensated autonomous
  execution.

## Known limitations

- Synthetic generation assumptions influence both labels and counterfactual ground truth.
- Real carrier, geography, warehouse and customer behaviour may have different distributions.
- No production fairness, drift or external-validity claim is made.
- The model is not causal; action-effect evidence comes from the separate synthetic
  counterfactual evaluation framework.
