# ADR-0002: Use a relational evidence ledger and compensatable local action gateway

- **Status:** Accepted
- **Date:** 2026-08-20

## Context

The first slice proved deterministic shadow decisioning but could not survive process restart,
manage approval, execute an action, verify external state or recover from partial failure.

## Decision

Version 0.2 introduces:

- SQLAlchemy persistence with PostgreSQL as the deployment target and SQLite for tests;
- Alembic migrations rather than runtime-only schema mutation;
- immutable decision records plus stateful approval/action records;
- deterministic idempotency keys tied to decision, action and policy version;
- a simulated systems-of-record adapter for local execution evidence;
- verify-before-retry for timeouts that may occur after provider state changed;
- compensating steps for partial reroute failure;
- independent outcome verification and one outcome record per decision.

The application remains a modular monolith. External brokers, Temporal and microservice splitting
are deferred until evidence shows the simpler design cannot meet the SLOs.

## Consequences

- The local workflow is reviewable without paid enterprise systems.
- PostgreSQL behaviour is exercised through migration CI.
- Exactly-once claims are avoided; the design provides idempotency plus verification.
- The simulator is evidence infrastructure, not a claim of real integration.
