# ADR-0005: Isolate OMS, WMS and carrier systems behind versioned adapter contracts

- **Status:** Accepted
- **Date:** 2026-08-21

## Context

Local V1 executed recovery actions through a single in-process simulator. That was sufficient
for governed-execution evidence, but a live OMS, WMS or carrier integration would otherwise
couple vendor payloads to optimiser and policy code.

## Decision

Introduce explicit adapter contracts and sandbox implementations:

- typed request/response schemas per system;
- a stable error taxonomy including ambiguous timeout, rate limit and malformed payload;
- one-attempt write retries with verify-before-retry after ambiguous outcomes;
- compensating actions for reroute, carrier upgrade and split shipment;
- correlation IDs and idempotency keys on every mutating call;
- contract version `v1`.

The action gateway depends on an operations port, not on vendor SDKs. Live HTTP adapters will
implement the same contracts when credentials exist.

## Consequences

- Core decision logic remains deterministic and vendor-neutral.
- Local tests can inject timeout, malformed and rate-limit failures without pretending a live
  integration exists.
- A future live adapter can be added without rewriting optimisation, policy or value attribution.
