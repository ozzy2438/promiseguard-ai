# Milestone 2 evidence — local production-like governed control loop

- **Evidence date:** 2026-08-20
- **Evidence classification:** production-like local implementation with synthetic data
- **Branch:** `chatgpt/project-prompt`
- **Cloud deployment:** intentionally deferred
- **OpenAI model integration:** intentionally deferred until the project owner supplies credentials

## Implemented scope

This milestone expands the first deterministic shadow slice into a local production-like control
loop with durable evidence and governed execution:

```text
validated operational event
→ durable inbox and canonical order context
→ calibrated or deterministic promise-risk score
→ counterfactual recovery simulation
→ constrained decision optimisation
→ versioned policy and evidence-bounded autonomy
→ human approval or bounded-autonomy gate
→ idempotent action execution
→ verify-before-retry after ambiguous timeout
→ compensation after partial failure
→ independent postcondition and outcome verification
→ immutable decision, execution, outcome and autonomy evidence
```

The implementation includes PostgreSQL-compatible persistence, Alembic migrations, synthetic data
and anomaly-labelled event generation, temporal model training, a human-approval workflow, a
persistent global kill switch, action-specific autonomy profiles, a local systems-of-record
simulator, outcome/value attribution, Prometheus metrics, a Streamlit operations console and dbt
analytical models.

## Local automated validation

| Check | Result |
|---|---:|
| Pytest | **53 passed** |
| Combined test coverage | **92.41%** |
| Configured minimum coverage | 88% |
| Python compile check | Passed |
| Python files over 100 characters | 0 |
| Clean SQLite migration to Alembic head | Passed |
| Tables after migration | 9 including `alembic_version` |
| 2,000-order synthetic CLI smoke | Passed |
| Synthetic events generated | 8,014 |
| Calibrated-logistic smoke training | Passed |
| Counterfactual value-evaluation smoke | Passed |
| Governed approval/execution/verification demo | Passed |

The migrated application tables are:

```text
actions
approvals
autonomy_evidence
autonomy_profiles
decisions
operational_events
outcomes
runtime_controls
```

## Failure and safety behaviour covered by tests

- duplicate source-event suppression and payload-conflict rejection;
- immutable decision and outcome fingerprint conflicts;
- duplicate action-request suppression;
- ambiguous provider timeout after a successful side effect;
- postcondition verification before retry;
- partial reroute followed by compensating restoration;
- approval expiry, role checks and delegated financial limits;
- bounded autonomy disabled until evidence requirements are met;
- global kill switch enforced at policy and execution boundaries;
- automatic action-profile suspension after failed or compensated autonomous execution;
- stale-data refusal or confidence downgrade;
- prompt injection embedded in operational notes ignored as authority;
- unsupported actions rejected through typed allow-listed contracts;
- PII and secret-key redaction in structured logs;
- correlation identifiers propagated through API responses and logs.

## 100,000-order synthetic model evidence

The evidence dataset was regenerated with fixed seed `20260820`.

- Records: **100,000**
- Temporal holdout: **20,000**
- Dataset SHA-256:
  `0234bac5db3cf1808f43a98013049cb2e1ce240666ae3bfcb984672640dd402b`
- Selected candidate: `calibrated_lightgbm`
- Model version: `risk-calibrated_lightgbm-3814942c3b36`
- PR-AUC: **0.4386643299**
- Holdout prevalence: **0.21685**
- ROC-AUC: **0.6911201255**
- Brier score: **0.1500251517**
- Expected calibration error: **0.0121521601**

The ranking performance is useful but moderate. It is synthetic evidence and does not establish
external validity or production performance.

## 100,000-order counterfactual decision evidence

- Optimal-action agreement with known synthetic ground truth: **95.043%**
- False-intervention rate: **4.6636%**
- Intervention rate: **41.513%**
- Mean on-time-probability uplift: **11.4922 percentage points**
- Mean regret per order: **A$0.06**
- P95 regret: **A$0.00**
- Simulated incremental value with intervention cost included: **A$646,663.53**
- Simulated intervention cost: **A$509,397.34**

Selected actions:

- `TAKE_NO_ACTION`: 58,487
- `CARRIER_UPGRADE`: 25,264
- `REROUTE`: 11,944
- `SPLIT_SHIPMENT`: 4,305

These values are classified as **synthetic counterfactual backtest evidence**. They are not real
company revenue and must never be presented as production savings.

## Independent review status

This milestone has strong automated and failure-injection evidence, but it has not yet passed an
independent human or separate-agent architecture/security review. It must therefore not be merged
to `main` solely because tests are green.

## Validation limitations

- Local validation ran on Python 3.13.5; CI targets Python 3.12.
- Ruff and mypy could not be installed in the isolated local environment because outbound package
  access was unavailable. They are configured as mandatory GitHub CI checks.
- Docker was not available in the local execution environment, so Docker Compose could be
  syntax-validated only after remote or developer-machine execution.
- PostgreSQL migration execution is configured in GitHub CI but local validation used SQLite.
- The provider adapters are simulated systems of record, not real warehouse or carrier APIs.
- OpenAI orchestration and AWS deployment are explicitly outside this milestone.

## Claim boundary

Acceptable description:

> Production-like local implementation with persistent governance, failure recovery and synthetic
> model/value evidence.

Unacceptable descriptions include:

- production-proven;
- live autonomous retailer deployment;
- real revenue saved;
- real customer outcomes;
- or completed AWS deployment.
