# ADR-0001: Begin with a deterministic shadow-mode vertical slice

- **Status:** Accepted
- **Date:** 2026-08-20

## Context

The authoritative project prompt requires a small closed loop before expanding into model
training, persistence, execution or cloud infrastructure. Building all subsystems at once
would make correctness and failure behaviour difficult to review.

## Decision

The first implementation uses a modular Python core with:

- strict Pydantic contracts;
- a transparent deterministic risk baseline;
- deterministic counterfactual calculations;
- explicit constrained ranking;
- a separate policy gateway;
- shadow-mode orchestration only;
- and an immutable in-memory ledger with idempotent replay.

No LLM or external write tool is used in this milestone. This is deliberate: the controlled
domain services and evidence path must exist before an AI orchestrator is permitted to call
them.

## Consequences

Positive:

- calculations are reproducible and reviewable;
- tests can exercise the full decision trace without paid services;
- no external system can be modified;
- later ML and agent components have stable contracts.

Limitations:

- no durable persistence;
- no trained risk model;
- no approval or execution workflow;
- no verified business outcome yet.
