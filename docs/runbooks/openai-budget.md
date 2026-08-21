# Runbook: OpenAI budget and bounded review

## Safe defaults

```bash
export OPENAI_MODEL=gpt-5-nano
export OPENAI_BUDGET_USD=3.00
export OPENAI_PER_RUN_LIMIT_USD=0.001
export OPENAI_MAX_OUTPUT_TOKENS=320
export OPENAI_TIMEOUT_SECONDS=30
```

`OPENAI_API_KEY` must already exist in the shell or secret store. Never place it in a tracked file.

## Inspect budget

```bash
curl -fsS http://localhost:8000/v1/agent/budget
```

The response shows configured limit, reserved cost, accounted spend and remaining application
budget. The system refuses a request before it would exceed either the per-run or project ceiling.

## Run one explicit smoke review

```bash
promiseguard-openai-smoke
```

This performs one structured review, does not advance the workflow and prints only safe run, token,
cost and validation metadata. The completed owner-run result is recorded in
`docs/assurance/openai-live-smoke.md`. Do not run another live smoke merely to refresh that
artifact.

## Respond to a budget block

1. Do not raise the budget automatically.
2. Inspect `/v1/agent/budget` and the relevant `/v1/agent/runs/{run_id}` record.
3. Confirm the model, prompt version, token usage and whether duplicate context should have reused a
   completed run.
4. Investigate unusually large input before changing limits.
5. Require explicit owner approval for any increase above US$3.00.

## Respond to a failed or rejected run

- `AGENT_OUTPUT_REJECTED`: keep the workflow unchanged and inspect validation errors.
- `OPENAI_REQUEST_FAILED:*`: treat provider result as ambiguous; the reservation is charged
  conservatively.
- `STALE_RESERVATION_CHARGED_CONSERVATIVELY`: investigate process interruption before retrying.
- unknown model pricing: review official pricing and add a tested explicit pricing entry; never
  guess.

## Reset policy

Do not delete or reset the budget row merely to regain spend. For local disposable development, use
a new database only when starting a clearly documented new test cycle. Production-like evidence
must retain the original budget and run history.
