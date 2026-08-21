# Runbook: action failure and manual recovery

1. Locate the decision and action through their correlation IDs.
2. Check action status and ordered step evidence.
3. For ambiguous timeout, read the external system of record before retrying.
4. If a reroute was compensated, confirm both:
   - order location is restored;
   - alternative reservation is released.
5. If compensation failed, activate the action kill switch in the future policy layer and open a
   manual recovery case. Do not issue a blind retry.
6. Record the human resolution and supporting external references.
7. Add the scenario to the regression and failure-injection suite.
