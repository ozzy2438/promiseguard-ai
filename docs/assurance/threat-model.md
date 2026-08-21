# Threat model — local production-like milestone

| Threat | Control | Evidence |
|---|---|---|
| Prompt injection in order notes | Notes are never interpreted as authority | hostile-note test |
| Duplicate source event | source identity/version and payload fingerprint | persistence conflict test |
| Duplicate business action | deterministic idempotency key and unique DB constraint | replay test |
| Timeout after provider success | postcondition read before retry | ambiguous-timeout test |
| Partial reroute | restore location and release alternative reservation | compensation test |
| Approval bypass | policy disposition, role and expiry checks | auditor/expiry tests |
| Unproven autonomous execution | approval-required default and consecutive-success gate | autonomy tests |
| Continued writes during incident | persistent global kill switch checked at policy and execution | kill-switch tests |
| Degraded autonomous action | automatic action-profile suspension and streak reset | compensation test |
| Stale operational data | confidence downgrade and policy block | vertical-slice test |
| Unsupported action | action allow-list and typed command schema | action gateway dispatch |
| Fabricated financial output | amounts come from deterministic services | simulator tests |
| Policy-state replay ambiguity | control-version fingerprint in decision identity | autonomy tests |
| Audit mutation | immutable decision/outcome fingerprint conflict | ledger tests |
| Synthetic-value overclaim | machine-readable evidence classification and claim limit | evidence JSON |
| Event-order anomalies | anomaly-labelled duplicate, late and out-of-order generator | event-stream tests |

## Residual risks

- The simulated provider does not prove real carrier or warehouse API semantics.
- Enterprise identity federation and separation of duties are not implemented.
- External append-only audit retention is not yet configured.
- Multi-process race behaviour is partially protected with database constraints and row locks but
  still requires PostgreSQL load and concurrency testing.
- Synthetic model quality does not establish external validity.
- AWS security, networking, backup and disaster recovery remain deferred until deployment.
