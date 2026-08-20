# PromiseGuard AI

> Protect the promise before it breaks.

PromiseGuard AI is a production-oriented reference implementation for detecting at-risk
orders, simulating recovery options, selecting the economically strongest feasible action,
applying policy controls and recording an auditable decision trace.

## Current milestone: first closed-loop vertical slice

This branch intentionally implements only:

```text
one typed order event
→ canonical order context
→ deterministic risk score
→ no-action + reroute + carrier-upgrade simulations
→ constrained recommendation
→ shadow-mode policy result
→ immutable in-memory ledger record
→ reproducible tests
```

It does **not** yet implement a trained ML model, PostgreSQL persistence, external action
execution, human approval, rollback, OpenAI model calls, synthetic data at scale or cloud
deployment. Those remain explicit later milestones.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
python scripts/demo_vertical_slice.py
uvicorn apps.api.main:app --reload
```

API endpoints:

- `GET /healthz`
- `POST /v1/shadow/evaluate`

## Design principles demonstrated

- strict typed contracts;
- deterministic and reproducible calculations;
- explicit no-action baseline;
- policy outside the orchestration layer;
- untrusted operational notes cannot change authority;
- immutable, idempotent decision recording;
- no claim of successful execution before independent verification exists.

The authoritative full project brief is in [`PROJECT_PROMPT.md`](PROJECT_PROMPT.md).
