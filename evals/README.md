# PromiseGuard OpenAI Agent Evals

The default harness is offline and deterministic. It exercises the real PromiseGuard decision,
budget, structured-output validation and workflow path through a fake Responses client; it makes
no provider call and spends nothing.

```bash
python evals/run_local.py
```

The live path is explicit, capped and never runs in normal CI:

```bash
python evals/run_local.py --live --max-cases 3
```

Requirements for live mode:

- `OPENAI_API_KEY` exists in the current shell;
- `OPENAI_MODEL` defaults to `gpt-5-nano`;
- application budget defaults to `US$3.00`;
- per-run reservation defaults to `US$0.001`;
- workflow advancement is disabled, so no operational write follows the model review.

Results are written to `evals/results/latest.json`. Provider text is accepted only after it matches
the immutable deterministic decision, policy disposition and allow-listed evidence identifiers.
