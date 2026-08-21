# ADR-0004: Use one budget-bounded Responses API review before governed workflow submission

- **Status:** Accepted
- **Date:** 2026-08-20

## Context

PromiseGuard already owns the deterministic decision loop: canonical context, risk scoring,
counterfactual simulation, constrained optimisation, policy, approval, execution, verification and
value attribution. Giving an LLM authority to repeat those calculations or directly execute tools
would duplicate trusted controls, increase cost and widen the failure surface.

The project owner set a maximum OpenAI development budget of **US$3.00** and requested the
lowest-cost suitable model. The integration must therefore remain useful when the API is absent,
must never run in ordinary CI and must block locally before a request can exceed the configured
budget.

## Decision

Use the OpenAI Responses API directly for one structured review call because PromiseGuard owns the
loop and needs a short-lived typed response rather than an SDK-managed multi-turn tool loop.

The review layer:

- defaults to `gpt-5-nano`;
- uses one request with a strict Pydantic output schema;
- sets `store=false`;
- limits output tokens;
- disables SDK retries;
- excludes customer identifiers and free-text operational notes;
- cannot alter the selected action, policy result or evidence allow-list;
- never performs calculations or calls operational adapters;
- is validated deterministically before workflow submission;
- and is optional, so all safety-critical controls continue without OpenAI.

A persistent application-level budget ledger reserves conservative worst-case cost before the
provider call and records actual usage afterwards. Unknown or ambiguous provider failures are
charged at the full reservation so a crash cannot silently reopen budget.

Default controls:

```text
OPENAI_MODEL=gpt-5-nano
OPENAI_BUDGET_USD=3.00
OPENAI_PER_RUN_LIMIT_USD=0.001
OPENAI_MAX_OUTPUT_TOKENS=320
OPENAI_TIMEOUT_SECONDS=30
```

## Consequences

### Positive

- hard local refusal before the configured application budget is exceeded;
- a single small model request instead of a potentially unbounded agent loop;
- deterministic action authority remains outside the model;
- completed identical reviews are reused without new spend;
- exact token and cost evidence is persisted;
- the system remains fully usable with the OpenAI layer disabled.

### Trade-offs

- this integration does not demonstrate a free-form multi-agent conversation;
- provider pricing must be explicitly reviewed before enabling another model;
- the application budget covers PromiseGuard-recorded calls, not unrelated usage of the same API
  project or key;
- a final live smoke run must occur in an environment that holds `OPENAI_API_KEY`.

The owner-run live smoke has been recorded as
`docs/assurance/evidence/openai-live-smoke-owner-run.json`. Further live calls are not required
for this assurance record.

## Rejected alternatives

- **Unbounded Agents SDK tool loop:** unnecessary because the application already owns the durable
  loop and tool authority; it adds turns and cost without improving control.
- **LLM-generated financial calculations:** rejected because outputs would not be reproducible.
- **Automatic live CI on every push:** rejected because it creates recurring spend and makes tests
  dependent on a remote model.
- **Relying only on a platform budget alert:** rejected because application-local enforcement and
  decision-level evidence are required.
