# Owner-run live OpenAI smoke evidence

## Classification

This document records **one owner-run live OpenAI structured review**. It is not offline
evaluation evidence, not a production accuracy claim, and not business-value evidence.

| Layer | What it proves | Artifact |
|---|---|---|
| Offline / CI eval | Fake Responses client, zero provider spend | `python evals/run_local.py`, `evals/README.md` |
| Deterministic validation | Schema, action, policy, evidence allow-list | unit tests + this smoke `validation_errors: []` |
| Application budget | US$3 ceiling enforced in-process | `src/promiseguard/openai_budget.py`, budget tests |
| Owner-run live API | One successful `gpt-5-nano` Responses call | `docs/assurance/evidence/openai-live-smoke-owner-run.json` |

## Recorded result

- **Model:** `gpt-5-nano`
- **Path:** structured review, `advance_workflow=false`
- **Status:** `COMPLETED` with no error
- **Deterministic validation:** passed (`validation_errors` empty)
- **Tokens:** 1,712 (1,472 input + 240 output)
- **Accounted cost:** US$0.000170
- **Application budget ceiling:** US$3.00 total
- **Spend after the run:** US$0.000170

The selected action `SPLIT_SHIPMENT` and disposition `REQUEST_APPROVAL` were copied from the
immutable decision packet. The model did not receive operational write tools.

## How this artifact was produced

The owner ran `promiseguard-openai-smoke` in a local environment that already held
`OPENAI_API_KEY`. The resulting run row was exported from the local evidence database into the
committed JSON artifact. **No additional paid call was made to create this documentation.**

Do not treat the gitignored local database as the assurance record. The committed JSON is the
repository evidence.

## Reproduction without another paid call

Inspect the committed artifact:

```bash
python -m json.tool docs/assurance/evidence/openai-live-smoke-owner-run.json
```

A further live call is only justified for a genuine engineering reason, remains manual, and must
stay inside the application-enforced US$3 ceiling.
