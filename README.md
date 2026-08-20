# PromiseGuard AI

> **Protect the promise before it breaks.**

PromiseGuard AI is a production-oriented reference implementation for detecting at-risk orders,
simulating counterfactual recovery options, selecting the strongest feasible action, applying
policy and human-approval controls, executing reversible interventions, independently verifying
outcomes and recording decision-level value evidence.

## Current milestone: local production-like control loop

This branch implements the following closed loop without OpenAI model calls or AWS deployment:

```text
source event
→ durable inbox and canonical typed context
→ deterministic or calibrated promise-risk scorer
→ no-action, reroute, carrier-upgrade and split-shipment simulation
→ constrained optimiser
→ versioned policy and evidence-bounded autonomy gateway
→ approval or bounded-autonomy decision
→ idempotent action execution
→ verify-before-retry for ambiguous provider timeouts
→ compensation after partial failure
→ independent delivery/outcome verification
→ immutable decision, outcome and autonomy evidence
→ synthetic counterfactual value backtest
```

### Implemented

- FastAPI application factory and strict Pydantic contracts;
- SQLite test mode and PostgreSQL-compatible SQLAlchemy schema;
- versioned Alembic migrations;
- deterministic event and decision replay protection;
- reproducible 100,000-order synthetic environment with known counterfactual ground truth;
- anomaly-labelled event streams for duplicate, late-arriving and out-of-order events;
- temporal calibrated logistic baseline and calibrated LightGBM candidate;
- counterfactual recovery simulation and constrained action selection;
- human approval with role checks and expiry;
- persistent global kill switch and action-specific autonomy profiles;
- manager-only autonomy changes with recorded rationale;
- 20-consecutive-success evidence gate before bounded autonomy;
- automatic action-profile suspension after failed or compensated autonomous execution;
- reroute, carrier upgrade and split-shipment adapters;
- idempotency, ambiguous-timeout verification and compensating actions;
- outcome/value ledger and machine-readable synthetic value evaluation;
- Prometheus metrics and a Streamlit operations console;
- dbt staging and decision-outcome mart definitions;
- Docker Compose for local PostgreSQL;
- CI, migration, persistence, model, security and failure-injection tests.

### Explicitly not implemented yet

- OpenAI API / Agents SDK orchestration;
- real retailer, carrier, payment or customer-message integrations;
- enterprise identity federation;
- AWS deployment;
- production revenue claims.

Synthetic and test results must always be labelled as simulated, backtested or production-like.

## Evidence snapshot

The committed evidence was reproduced with seed `20260820` and 100,000 synthetic orders.

### Promise-risk model

- Selected model: calibrated LightGBM
- Temporal holdout: 20,000 orders
- PR-AUC: 0.4387 versus 0.2169 holdout prevalence
- ROC-AUC: 0.6911
- Brier score: 0.1500
- Expected calibration error: 0.0122

### Counterfactual decision evaluation

- Optimal-action agreement: **95.043%**
- False-intervention rate: **4.664%**
- Mean on-time probability uplift: **11.492 percentage points**
- Mean regret per order: **A$0.06**
- Synthetic incremental value, intervention cost included: **A$646,663.53**

These figures are synthetic backtest evidence, not real company revenue. See
`docs/assurance/evidence/` and `docs/assurance/value-evaluation.md` for exact machine-readable
reports and claim boundaries.

Local milestone validation, failure coverage and environment limitations are recorded in
`docs/assurance/milestone-2-evidence.md`.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,ml,postgres]"
pytest
```

Run the API with local SQLite:

```bash
export DATABASE_URL=sqlite+pysqlite:///./promiseguard.db
export AUTO_CREATE_SCHEMA=true
uvicorn apps.api.main:create_app --factory --reload
```

API documentation is then available through FastAPI at `/docs`.

## Local PostgreSQL

```bash
docker compose up --build
```

The API applies Alembic migrations before starting. The password in `docker-compose.yml` is
intentionally development-only.

## Synthetic data, model and value evidence

```bash
promiseguard-generate \
  --count 100000 \
  --seed 20260820 \
  --output data/generated/orders.jsonl

promiseguard-generate-events \
  --input data/generated/orders.jsonl \
  --output data/generated/events.jsonl

promiseguard-train \
  --input data/generated/orders.jsonl \
  --output-dir artifacts/models

promiseguard-evaluate-value \
  --input data/generated/orders.jsonl \
  --model-path artifacts/models/risk_model.joblib \
  --output artifacts/evidence/value_evaluation.json
```

Activate a trained artifact at runtime:

```bash
export RISK_MODEL_PATH=artifacts/models/risk_model.joblib
uvicorn apps.api.main:create_app --factory --reload
```

## Governed workflow demo

```bash
python scripts/demo_governed_workflow.py
```

The deterministic demo selects an executable intervention, creates an approval, executes through
the governed action gateway and records an independently verified outcome.

## Operations console

```bash
pip install -e ".[ui]"
streamlit run apps/operations_console/app.py
```

The console exposes decisions, approvals, decision traces, the global kill switch and action
profiles. It is an operations review interface rather than a chat UI.

## Analytics layer

The `dbt/` project builds staging views and `fct_decision_outcomes`, joining immutable decisions,
actions and verified outcomes for value attribution and assurance.

## Repository truthfulness

The authoritative project constraints remain in `PROJECT_PROMPT.md`. Green tests alone are not
considered sufficient evidence. Major milestones require failure injection, machine-readable
evidence, explicit claim boundaries and independent review before merge.
