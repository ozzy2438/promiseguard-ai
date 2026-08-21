# Pilot, shadow and approval-mode readiness

The product can support a future shadow-mode and approval-mode UAT. This document does **not**
record UAT results. No operational users have run the system.

## What the local product already supports

| UAT need | Local support |
|---|---|
| Shadow decisions without execution | `OperatingMode.SHADOW` and `POST /v1/shadow/evaluate` |
| Human review | Streamlit console + pending approval APIs |
| Decision rationale | Ranked options, policy reasons, optional bounded OpenAI review |
| Baseline comparison | Explicit `TAKE_NO_ACTION` in every recommendation |
| Proposed action | `recommendation.selected_action` |
| Expected value | `expected_incremental_value_vs_no_action` |
| Risk / policy reason | `risk` and `policy.reasons` |
| Approval / rejection | `/v1/approvals/{id}/approve` and `/reject` |
| Outcome tracking | Independent verification + outcome ledger |
| Operator feedback | `POST /v1/decisions/{id}/feedback` |
| Audit trail | Immutable decisions, approvals, actions, outcomes, OpenAI runs |

## What requires real operational users

- Agreement that shadow recommendations are useful in a live order flow.
- Approval-mode UAT with managers who own real recovery authority.
- Feedback volume large enough to judge false-positive cost.
- Assignment of a control or matched comparison group.
- Confirmation that local roles map onto the retailer's job titles.

Until those activities happen, the system remains **pre-pilot**. Do not label it pilot-ready
merely because the APIs exist.
