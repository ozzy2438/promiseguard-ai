# OpenAI review-layer threat model

| Threat | Control | Evidence |
|---|---|---|
| Prompt injection in order notes | Free-text notes are excluded from model context | agent minimisation tests |
| Model changes selected action | Exact equality check against immutable decision | rejected-output test |
| Model invents evidence | Evidence allow-list and strict validation | unsupported-evidence test path |
| Unsupported financial claim | Summary rejects digits and currency symbols; calculations stay local | Pydantic contract tests |
| Model bypasses approval | Policy disposition and next-step equality checks | workflow non-advancement tests |
| Duplicate provider spend | Context fingerprint and completed-run reuse | reuse test |
| Retry storm | OpenAI SDK retries disabled; one request per reservation | adapter configuration |
| Crash after provider acceptance | reservation TTL is charged conservatively | stale-reservation test |
| Budget exhaustion | PostgreSQL row lock plus pre-call reservation | budget guard tests |
| Secret exposure | key is read from environment only and absent from settings/logs | configuration test and `.gitignore` |
| Provider data retention | Responses request uses `store=false` | adapter code review |
| Unreviewed model price | unknown model pricing raises before reservation | pricing test |
