"""Local identity, role binding and tenant helpers.

This is not enterprise IAM. It provides an explicit local directory, optional
strict binding of actor IDs to roles, and a default tenant boundary so the
product does not silently pretend that federation already exists.
"""

from __future__ import annotations

import os

from promiseguard.adapters.contracts import DEFAULT_TENANT_ID
from promiseguard.models import UserRole

LOCAL_IDENTITY_DIRECTORY: dict[str, UserRole] = {
    "operations-manager-ui": UserRole.OPERATIONS_MANAGER,
    "operations-analyst-ui": UserRole.OPERATIONS_ANALYST,
    "auditor-ui": UserRole.AUDITOR,
    "promiseguard-service": UserRole.SERVICE_IDENTITY,
    "openai-smoke": UserRole.SERVICE_IDENTITY,
    "eval-runner": UserRole.SERVICE_IDENTITY,
}


class IdentityError(RuntimeError):
    """Raised when a local actor/role binding is invalid."""


def strict_local_identity_enabled() -> bool:
    raw = os.getenv("PROMISEGUARD_STRICT_LOCAL_IDENTITY", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def bind_claimed_role(
    actor_id: str,
    claimed_role: UserRole,
    *,
    strict: bool | None = None,
) -> UserRole:
    """Return the authorised role for an actor.

    Registered local identities cannot claim a different role. Unknown actors are
    permitted only when strict local identity is disabled (tests and ad-hoc
    local use).
    """

    enforce_strict = strict_local_identity_enabled() if strict is None else strict
    registered = LOCAL_IDENTITY_DIRECTORY.get(actor_id)
    if registered is not None:
        if claimed_role is not registered:
            raise IdentityError(
                f"actor {actor_id!r} is registered as {registered.value} and cannot "
                f"claim {claimed_role.value}"
            )
        return registered
    if enforce_strict:
        raise IdentityError(f"actor {actor_id!r} is not in the local identity directory")
    return claimed_role


def assert_separation_of_duties(*, requested_by: str, decided_by: str) -> None:
    if requested_by == decided_by:
        raise IdentityError("requester cannot approve or reject their own request")


def normalise_tenant_id(tenant_id: str | None) -> str:
    candidate = (tenant_id or DEFAULT_TENANT_ID).strip()
    if not candidate:
        return DEFAULT_TENANT_ID
    return candidate[:80]
