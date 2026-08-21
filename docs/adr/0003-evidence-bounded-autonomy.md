# ADR-0003: Make autonomy persistent, evidence-bounded and automatically revocable

- **Status:** Accepted
- **Date:** 2026-08-20

## Context

A cost threshold alone does not justify autonomous write access. The system needs a persistent,
auditable answer to three questions:

1. Is global execution currently safe?
2. Has this specific action class earned bounded autonomy?
3. Should a failure immediately reduce its authority?

## Decision

Implement:

- a database-backed global action kill switch;
- one autonomy profile per executable action;
- manager-only profile and kill-switch changes with recorded rationale;
- a requirement for 20 consecutive independently verified successful outcomes before promotion;
- idempotent evidence records;
- control-version fingerprints included in immutable decision identity;
- and automatic suspension after a failed, compensated or manual-recovery autonomous action.

Historical success and failure totals remain visible, while promotion uses consecutive success so
an action can recover after remediation and a new evidence streak. Human approval remains the
default state.

## Consequences

- A model or agent cannot grant itself authority.
- Approval and autonomy changes survive process restart.
- Re-evaluating the same event after a control change creates a distinct immutable decision.
- One historical failure does not permanently ban recovery, but a fresh evidence threshold is
  required.
- Real production use would additionally require enterprise identity, separation of duties and
  external audit-log retention.
