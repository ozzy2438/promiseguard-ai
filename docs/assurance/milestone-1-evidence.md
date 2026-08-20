# Milestone 1 Assurance Evidence

## Exact scope

One order-risk event is validated and evaluated through risk scoring, three counterfactual
options, deterministic optimisation, shadow-mode policy and immutable ledger recording.

## Acceptance evidence

The automated tests demonstrate:

1. an at-risk order selects rerouting when it has the highest expected net value;
2. `TAKE_NO_ACTION` remains selectable when interventions destroy value;
3. stale operational context is blocked;
4. replaying the same event is deterministic and does not create a duplicate decision;
5. a conflicting replay is rejected;
6. malicious text embedded in an operational note cannot bypass policy;
7. unknown request fields are rejected;
8. the API returns the same structured decision trace.

## Explicit non-goals

- model training or claims of ML performance;
- external tool execution;
- human approval;
- compensation or rollback;
- PostgreSQL, dbt, event broker or AWS deployment;
- production-value claims.

## Reproduce

```bash
pip install -e ".[dev]"
pytest
python scripts/demo_vertical_slice.py
```

Passing tests are necessary but not sufficient. This milestone still requires independent
review of the economics, threat assumptions and contract boundaries before scope expands.
