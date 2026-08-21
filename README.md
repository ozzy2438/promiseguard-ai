# PromiseGuard AI

> **Protect the promise before it breaks.**

PromiseGuard AI is a production-oriented reference implementation for detecting at-risk orders,
simulating counterfactual recovery options, selecting the strongest feasible action, applying
policy and human-approval controls, executing reversible interventions, independently verifying
outcomes and recording decision-level value evidence.

## Current milestone: complete local production-like reference implementation

This branch now implements the complete local Version 1 control loop, excluding only real external
enterprise integrations and AWS deployment:

```text
source event
→ durable inbox and canonical typed context
→ deterministic or calibrated promise-risk scorer
→ no-action, reroute, carrier-upgrade and split-shipment simulation
→ constrained optimiser
→ versioned policy and evidence-bounded autonomy gateway
→ optional budget-bounded OpenAI structured review
→ approval or bounded-autonomy decision
→ idempotent action execution
→ verify-before-retry for ambiguous provider timeouts
→ compensation after partial failure
→ independent delivery/outcome verification
→ immutable decision, outcome, autonomy and cost evidence
→ synthetic counterfactual value backtest
```

## Implemented

### Data, ML and decisioning

- FastAPI application factory and strict Pydantic contracts;
- SQLite test mode and PostgreSQL-compatible SQLAlchemy schema;
- versioned Alembic migrations;
- deterministic event and decision replay protection;
- reproducible 100,000-order synthetic environment with known counterfactual ground truth;
- anomaly-labelled event streams for duplicate, late-arriving and out-of-order events;
- temporal calibrated logistic baseline and calibrated LightGBM candidate;
- counterfactual recovery simulation and constrained action selection;
- explicit `TAKE_NO_ACTION` baseline.

### Governed execution

- human approval with role checks and expiry;
- persistent global kill switch and action-specific autonomy profiles;
- manager-only autonomy changes with recorded rationale;
- evidence gate before bounded autonomy;
- automatic profile suspension after failed or compensated autonomous execution;
- reroute, carrier-upgrade and split-shipment adapters with versioned OMS/WMS/carrier contracts;
- idempotency, ambiguous-timeout verification and compensating actions for all three writes;
- independent postcondition and outcome verification.

### Budget-bounded OpenAI layer

- one structured Responses API review call rather than an unbounded model loop;
- default model `gpt-5-nano`, configurable by environment;
- application-enforced project ceiling of **US$3.00** by default;
- conservative per-run reservation ceiling of **US$0.001** by default;
- persistent run, token, response, validation and cost evidence;
- completed identical context reused without another provider request;
- provider retries disabled;
- provider storage disabled with `store=false`;
- customer IDs and operational free-text notes excluded from model context;
- deterministic rejection when the model changes action, policy or evidence;
- no operational write unless the existing local workflow separately permits it;
- no live request in ordinary CI.

The OpenAI layer is optional. The entire safety-critical decision and execution system continues to
work when it is disabled or no key is present.

### Analytics and operations

- outcome/value ledger and machine-readable synthetic value evaluation;
- Prometheus metrics and a Streamlit operations console;
- dbt decision-outcome, autonomy-assurance and OpenAI cost-assurance marts;
- Docker Compose for local PostgreSQL;
- CI, migration, persistence, model, security, budget and failure-injection tests;
- ADRs, threat models, runbooks, model card and assurance evidence.

## Explicitly not implemented yet

- real retailer, carrier, payment or customer-message integrations;
- enterprise identity federation;
- AWS deployment;
- production revenue claims;
- operational UAT results.

Synthetic and test results must always be labelled as simulated, backtested or production-like.
The live OpenAI provider path has an owner-run smoke artifact for `gpt-5-nano` (1,712 tokens,
US$0.000170, deterministic validation passed). See `docs/assurance/openai-live-smoke.md`. Offline
CI still never calls the provider. Do not treat that smoke result as production accuracy or
business-value evidence.

## Evidence snapshot

The committed data/ML evidence was reproduced with seed `20260820` and 100,000 synthetic orders.

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

## Local setup

Supported local runtime is **Python 3.12**. See `docs/engineering/python-runtime.md`.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,ml,postgres,agent]"
make python-version
pytest -m "not live_openai"
python evals/run_local.py
```

Run the API with local SQLite:

```bash
export DATABASE_URL=sqlite+pysqlite:///./promiseguard.db
export AUTO_CREATE_SCHEMA=true
uvicorn apps.api.main:create_app --factory --reload
```

API documentation is available at `/docs`.

## Local PostgreSQL and Docker

```bash
docker compose up --build
```

The API applies Alembic migrations before starting. Streamlit defaults to `8501`. PostgreSQL is
published on host port `5433` so it does not collide with a local Postgres on `5432`. API/console
host ports can be overridden with `PROMISEGUARD_API_PORT` and `PROMISEGUARD_CONSOLE_PORT`. The
password in `docker-compose.yml` is intentionally development-only. When `OPENAI_API_KEY` is exported in the
launching shell, Compose passes it to the API container without writing it into the repository.

Prove the integrated stack, including restart persistence:

```bash
python3.12 scripts/local_e2e.py --wait-seconds 120
docker compose restart api
python3.12 scripts/local_e2e.py --replay --wait-seconds 120
```

## OpenAI budget configuration

Safe defaults:

```bash
export OPENAI_ENABLED=auto
export OPENAI_MODEL=gpt-5-nano
export OPENAI_BUDGET_USD=3.00
export OPENAI_PER_RUN_LIMIT_USD=0.001
export OPENAI_MAX_OUTPUT_TOKENS=320
export OPENAI_TIMEOUT_SECONDS=30
```

`OPENAI_API_KEY` must be supplied only through the shell or a secret store.

Inspect the local hard guard:

```bash
curl -fsS http://localhost:8000/v1/agent/budget
```

Run exactly one explicit live structured review without advancing the workflow:

```bash
promiseguard-openai-smoke
```

Run offline evals at zero provider cost:

```bash
python evals/run_local.py
```

Run up to three explicit live eval cases:

```bash
python evals/run_local.py --live --max-cases 3
```

The GitHub live-eval workflow is manual only and requires the operator to type `RUN`; push and pull
request CI never call the OpenAI API.

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

The console exposes decisions, approvals, decision traces, the global kill switch, autonomy
profiles and the application-enforced OpenAI budget. It is an operations review interface rather
than a chat UI.

## Analytics layer

The `dbt/` project builds staging views and the following assurance marts:

- `fct_decision_outcomes`;
- `fct_autonomy_assurance`;
- `fct_openai_cost_assurance`.

## Repository truthfulness

The authoritative project constraints remain in `PROJECT_PROMPT.md`. Green tests alone are not
considered sufficient evidence. Major milestones require failure injection, machine-readable
evidence, explicit claim boundaries and independent review before merge.
