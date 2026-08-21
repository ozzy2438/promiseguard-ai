# Identity, RBAC and tenant isolation

## Implemented locally

- Roles: `OPERATIONS_ANALYST`, `OPERATIONS_MANAGER`, `AUDITOR`, `SERVICE_IDENTITY`.
- Approval authority: auditors and service identities cannot decide approvals.
- Delegated analyst cost limit: A$20; restricted products require a manager.
- Manager-only kill switch and autonomy-profile changes.
- Separation of duties: the requester cannot approve or reject their own request.
- Local identity directory for console and service actors. A registered actor cannot claim a
  different role.
- Optional strict mode (`PROMISEGUARD_STRICT_LOCAL_IDENTITY=true`) rejects unknown actor IDs.
  Docker Compose enables this. Ordinary tests remain permissive so fixture actors such as
  `manager-1` keep working.
- Default tenant `local-default` on every order and decision. Decision lists can be filtered by
  `tenant_id` query parameter or `X-Tenant-ID`.

## Explicitly not implemented (pilot / deployment)

- Enterprise identity federation (OIDC, SAML, IAM Identity Center).
- Token or session authentication on the API.
- Binding of HTTP credentials to `actor_id` (the body still carries the actor in local mode).
- Per-tenant database schemas or row-level security policies.
- Privileged admin role distinct from operations manager.
- Cross-tenant encryption or data residency controls.

The local directory is a stepping stone so role spoofing is visible and testable. It is not a
substitute for SSO. Enabling federation should replace client-asserted roles, not sit beside them
as a second source of truth.
