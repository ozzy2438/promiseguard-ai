# OpenAI structured-review assurance

## Boundary

The model is a bounded reviewer and intent formatter. It is not the optimiser, policy authority,
system of record or action executor.

The provider receives only a minimized immutable decision packet. It does not receive:

- customer identifiers;
- external order notes;
- arbitrary user instructions;
- database credentials;
- raw SQL;
- or operational write tools.

## Required invariants

A model response is rejected unless all of the following hold:

1. decision ID matches the immutable ledger;
2. selected action matches the deterministic optimiser;
3. policy disposition matches the policy gateway;
4. next step is implied by policy;
5. human-attention flag matches the policy boundary;
6. every evidence ID exists in the supplied allow-list;
7. the required rationale code is present;
8. the summary contains no independent numeric or currency claim.

Rejected output is persisted as evidence and cannot advance the workflow.

## Cost controls

- default project ceiling: US$3.00;
- default conservative per-run ceiling: US$0.001;
- maximum output: 320 tokens;
- no automatic provider calls in normal CI;
- identical completed context is reused without another request;
- ambiguous request failure is charged at the reserved amount;
- stale reservations are conservatively moved to spent cost.

## Evaluation layers

### Unit and integration tests

Cover model pricing, conservative reservations, budget exhaustion, stale reservations, output
validation, PII/free-text minimisation, cached-run reuse, provider timeout, workflow non-advancement
and API error behavior.

### Offline eval harness

`python evals/run_local.py` exercises the real decision, budget, validation and workflow path with a
fake Responses client. It spends nothing and is mandatory in CI.

### Explicit live eval

`python evals/run_local.py --live --max-cases 3` exercises the real provider path. It requires an
existing shell key, never advances the operational workflow, and respects the application budget.

The GitHub live workflow is `workflow_dispatch` only and additionally requires the operator to type
`RUN`. It is never triggered by push or pull request.

## Claim boundary

Offline documentation may claim:

- provider adapter implemented;
- structured output schema validated offline;
- application budget enforcement tested;
- live execution ready.

The owner-run live smoke in `docs/assurance/evidence/openai-live-smoke-owner-run.json` additionally
records that one `gpt-5-nano` structured review completed, passed deterministic validation, used
1,712 tokens and cost US$0.000170 under the US$3 application ceiling.

It must not claim that a model achieved a production accuracy rate, that real business value was
created, or that further live calls were made.
