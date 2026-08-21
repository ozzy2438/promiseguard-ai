# External adapter contracts

## Decision

OMS, WMS and carrier integrations are isolated behind versioned adapter contracts. Core
decisioning, optimisation, policy, approval and value attribution never import vendor SDKs.

Live retailer credentials are not present in this repository. The implemented adapters are
**sandbox implementations of production-grade contracts**, not claims of a live integration.

## Boundary

```text
PromiseGuardOrchestrator / PolicyGateway
        |
RecoveryWorkflowService / ActionGateway
        |
OperationsPort (vendor-neutral)
        |
  +-----+-----+
  |     |     |
 WMS   OMS  Carrier
sandbox sandbox sandbox
```

Reroute is a two-system saga (WMS reservation + OMS location change) coordinated by the gateway.
Compensation, verify-before-retry and idempotency remain gateway responsibilities.

## Contract contents

Each system contract in `src/promiseguard/adapters/contracts.py` defines:

- request and response schemas;
- authentication boundary (service identity to the external system);
- timeout and retry policy (writes default to one attempt);
- idempotency-key semantics;
- correlation identifiers;
- expected postconditions;
- ambiguous-timeout handling;
- compensating actions;
- rate-limit expectation;
- observability fields;
- error classification;
- audit evidence;
- contract version `v1`.

Ambiguous write outcomes are never retried blindly. The gateway reads the postcondition first.

## What is still required for a live sandbox

- owner-supplied OMS/WMS/carrier endpoints and credentials;
- mTLS or OAuth client configuration in a secret store;
- per-environment rate-limit and timeout tuning;
- a durable outbox if the live vendor cannot honour idempotency keys.

Until those exist, tests and the local stack must continue to use the sandbox adapters.
