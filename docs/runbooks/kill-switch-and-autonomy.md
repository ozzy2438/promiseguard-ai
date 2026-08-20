# Runbook: kill switch and autonomy suspension

## Activate the global kill switch

Use this when duplicate actions, provider ambiguity, unexpected financial impact, stale data or
policy bypass is suspected.

1. Record the incident identifier and concise reason.
2. Activate `POST /v1/controls/kill-switch` as an operations manager.
3. Confirm `/readyz` reports `kill_switch=true`.
4. Confirm new bounded-autonomy decisions return `GLOBAL_ACTION_KILL_SWITCH_ACTIVE`.
5. Do not cancel already completed provider actions without checking systems of record.
6. Triage in-flight actions using decision, action and provider correlation identifiers.

## Automatic action-profile suspension

A failed or compensated autonomous action changes only that action profile to `SUSPENDED`, resets
its consecutive-success streak and records an automatic reason. Other actions remain at their
existing levels unless the global kill switch is also activated.

## Restore service safely

1. Resolve the underlying incident and add a regression/failure-injection test.
2. Keep the affected action in approval-required mode while collecting fresh verified outcomes.
3. Require the configured consecutive-success threshold.
4. Obtain an explicit manager decision and rationale before promotion.
5. Deactivate the global kill switch only after in-flight state and provider postconditions are
   reconciled.
