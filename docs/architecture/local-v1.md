# Local production-like architecture

```text
FastAPI / Streamlit
       |
Evaluation Service ---------> Durable Event Inbox
       |                              |
Risk -> Simulator -> Optimiser -> Versioned Policy Gateway
       |                              |
Immutable Decision Ledger             +----> Kill Switch
       |                              +----> Action Autonomy Profile
Approval Service ----------------------+            |
       |                                           evidence gate
Governed Action Gateway -> simulated OMS / WMS / carrier state
       |                         |
       +-- deterministic idempotency
       +-- verify-before-retry
       +-- compensation on partial failure
       |
Outcome Verification -> Outcome Ledger -> Autonomy Evidence
       |                                      |
       +----> dbt decision-outcome mart        +--> automatic suspension
       |
Synthetic counterfactual evaluator -> machine-readable value report
```

## Boundaries

- OpenAI orchestration is a budget-bounded structured-review layer. Deterministic authority stays
  outside the model. Owner-run live smoke evidence is recorded separately from offline evals.
- Numerical decisions are deterministic or model-backed.
- Policy and autonomy are code and persistent data, not prompt instructions.
- External state is mutated only through the governed action gateway and versioned adapter
  contracts. Sandbox OMS/WMS/carrier adapters are not live enterprise integrations.
- A successful tool response is not a verified business outcome.
- The simulator is evidence infrastructure, not a claim of real enterprise integration.
- PostgreSQL is the target store; SQLite exists for fast isolated tests.
- AWS deployment is intentionally deferred. See `docs/architecture/aws-readiness.md`.
