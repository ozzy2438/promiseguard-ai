"""Prove the local Docker/PostgreSQL/FastAPI/Streamlit stack end to end.

This script talks to a running Compose stack. It does not start Docker itself.
It never calls the OpenAI API.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

DEFAULT_API = os.getenv("PROMISEGUARD_API_URL", "http://127.0.0.1:8000").rstrip("/")
DEFAULT_CONSOLE = os.getenv("PROMISEGUARD_CONSOLE_URL", "http://127.0.0.1:8501").rstrip("/")
STATE_PATH = Path(os.getenv("PROMISEGUARD_E2E_STATE", "/tmp/promiseguard-e2e-last.json"))


def _request(
    method: str,
    url: str,
    *,
    payload: dict[str, object] | None = None,
    timeout: float = 20,
    headers: dict[str, str] | None = None,
) -> tuple[int, object]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Accept": "application/json"}
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            parsed: object = json.loads(raw) if raw else {}
            return response.status, parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw.decode("utf-8", errors="replace")}
        return exc.code, parsed


def _wait_for_api(api_url: str, wait_seconds: int) -> dict[str, object]:
    deadline = time.time() + wait_seconds
    last_error = "not attempted"
    while time.time() < deadline:
        try:
            status, payload = _request("GET", f"{api_url}/readyz")
            if status == 200 and isinstance(payload, dict) and payload.get("status") == "ready":
                return payload
            last_error = f"status={status} payload={payload}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(2)
    raise SystemExit(f"API was not ready within {wait_seconds}s: {last_error}")


def _console_reachable(console_url: str) -> bool:
    try:
        req = urllib.request.Request(console_url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as response:
            return 200 <= response.status < 400
    except Exception:
        return False


def _order_payload(suffix: str, *, tenant_id: str) -> dict[str, object]:
    now = datetime.now(UTC)
    promised = now + timedelta(hours=18)
    return {
        "event": {
            "source_system": "oms",
            "event_id": f"evt-e2e-{suffix}",
            "event_version": 1,
            "event_type": "ORDER_RISK_EVALUATION_REQUESTED",
            "event_time": (now - timedelta(minutes=2)).isoformat(),
            "ingestion_time": (now - timedelta(minutes=1)).isoformat(),
            "schema_version": "v1",
            "deduplication_key": f"oms:evt-e2e-{suffix}:v1",
        },
        "order": {
            "order_id": f"order-e2e-{suffix}",
            "evaluation_time": now.isoformat(),
            "promised_delivery_at": promised.isoformat(),
            "gross_margin": "72.00",
            "cancellation_cost": "20.00",
            "support_cost": "8.00",
            "inventory_reserved": True,
            "inventory_available": False,
            "inventory_confidence": 0.95,
            "carrier_on_time_probability": 0.58,
            "hours_since_expected_scan": 3.5,
            "alternative_location_available": True,
            "reroute_on_time_probability": 0.92,
            "carrier_upgrade_on_time_probability": 0.84,
            "reroute_cost": "8.00",
            "carrier_upgrade_cost": "17.00",
            "data_freshness_minutes": 3,
            "source_references": [
                {
                    "system": "oms",
                    "record_id": f"order-e2e-{suffix}",
                    "observed_at": now.isoformat(),
                }
            ],
            "sku": "SKU-00001",
            "quantity": 1,
            "current_fulfilment_location": "FC-MEL",
            "alternative_location_id": "FC-SYD",
            "current_carrier_service": "STANDARD",
            "upgraded_carrier_service": "EXPRESS",
            "tenant_id": tenant_id,
        },
        "mode": "APPROVAL",
    }


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise SystemExit(message)


def _run_fresh(api_url: str, console_url: str) -> dict[str, object]:
    suffix = uuid4().hex[:12]
    tenant_id = "local-default"
    payload = _order_payload(suffix, tenant_id=tenant_id)
    status, decision = _request("POST", f"{api_url}/v1/evaluate", payload=payload)
    _require(status == 200 and isinstance(decision, dict), f"evaluate failed: {status} {decision}")
    decision_id = str(decision["decision_id"])
    _require(
        decision["recommendation"]["selected_action"]
        in {"REROUTE", "CARRIER_UPGRADE", "SPLIT_SHIPMENT"},
        f"expected an executable action, got {decision['recommendation']['selected_action']}",
    )

    listed_status, listed = _request(
        "GET",
        f"{api_url}/v1/decisions?limit=20&tenant_id={tenant_id}",
    )
    _require(listed_status == 200 and isinstance(listed, list), "decision list failed")
    _require(any(item["decision_id"] == decision_id for item in listed), "decision not persisted")

    status, submitted = _request(
        "POST",
        f"{api_url}/v1/decisions/{decision_id}/submit",
        payload={"actor_id": "operations-analyst-ui"},
    )
    _require(status == 200 and isinstance(submitted, dict), f"submit failed: {status} {submitted}")
    approval = submitted["approval"]
    _require(approval["status"] == "PENDING", "approval was not pending")

    status, replay_submit = _request(
        "POST",
        f"{api_url}/v1/decisions/{decision_id}/submit",
        payload={"actor_id": "operations-analyst-ui"},
    )
    _require(status == 200 and isinstance(replay_submit, dict), "idempotent submit failed")
    _require(
        replay_submit["approval"]["approval_id"] == approval["approval_id"],
        "submit was not idempotent",
    )

    status, approved = _request(
        "POST",
        f"{api_url}/v1/approvals/{approval['approval_id']}/approve",
        payload={
            "actor_id": "operations-manager-ui",
            "actor_role": "OPERATIONS_MANAGER",
            "reason": "Local stack end-to-end validation",
        },
    )
    _require(status == 200 and isinstance(approved, dict), f"approve failed: {status} {approved}")
    _require(approved["execution"]["status"] == "SUCCEEDED", "execution did not succeed")

    observed_at = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    status, verified = _request(
        "POST",
        f"{api_url}/v1/decisions/{decision_id}/verify",
        payload={
            "order_id": f"order-e2e-{suffix}",
            "delivered_on_time": True,
            "observed_at": observed_at,
            "source_reference": {
                "system": "carrier",
                "record_id": f"delivered:order-e2e-{suffix}",
                "observed_at": observed_at,
            },
        },
    )
    _require(status == 200 and isinstance(verified, dict), f"verify failed: {status} {verified}")
    _require(verified["outcome"]["status"] == "VERIFIED", "outcome was not independently verified")
    _require(
        Decimal(str(verified["outcome"]["estimated_incremental_value"])) != Decimal("0")
        or verified["outcome"]["on_time_delivery_observed"] is True,
        "value evidence missing from outcome",
    )

    status, feedback = _request(
        "POST",
        f"{api_url}/v1/decisions/{decision_id}/feedback",
        payload={
            "actor_id": "operations-analyst-ui",
            "actor_role": "OPERATIONS_ANALYST",
            "useful": True,
            "comment": "Local E2E operator review of the governed recovery.",
        },
    )
    _require(status == 200, f"feedback failed: {status} {feedback}")

    metrics_req = urllib.request.Request(f"{api_url}/metrics")
    with urllib.request.urlopen(metrics_req, timeout=10) as metrics:
        metrics_body = metrics.read().decode("utf-8")
    _require("promiseguard_decisions_total" in metrics_body, "decision metrics missing")
    _require("promiseguard_actions_total" in metrics_body, "action metrics missing")

    status, kill = _request(
        "POST",
        f"{api_url}/v1/controls/kill-switch",
        payload={
            "active": True,
            "actor_id": "operations-manager-ui",
            "actor_role": "OPERATIONS_MANAGER",
            "reason": "E2E kill-switch probe",
        },
    )
    _require(
        status == 200 and isinstance(kill, dict) and kill["active"] is True,
        "kill switch on failed",
    )
    blocked_suffix = uuid4().hex[:12]
    blocked_payload = _order_payload(blocked_suffix, tenant_id=tenant_id)
    status, blocked_decision = _request("POST", f"{api_url}/v1/evaluate", payload=blocked_payload)
    _require(status == 200 and isinstance(blocked_decision, dict), "blocked evaluate failed")
    status, blocked_submit = _request(
        "POST",
        f"{api_url}/v1/decisions/{blocked_decision['decision_id']}/submit",
        payload={"actor_id": "operations-analyst-ui"},
    )
    _require(status == 200 and isinstance(blocked_submit, dict), "blocked submit failed")
    status, blocked_approve = _request(
        "POST",
        f"{api_url}/v1/approvals/{blocked_submit['approval']['approval_id']}/approve",
        payload={
            "actor_id": "operations-manager-ui",
            "actor_role": "OPERATIONS_MANAGER",
            "reason": "Should be blocked by kill switch",
        },
    )
    _require(status == 409, f"kill switch did not block execution: {status} {blocked_approve}")
    status, restored = _request(
        "POST",
        f"{api_url}/v1/controls/kill-switch",
        payload={
            "active": False,
            "actor_id": "operations-manager-ui",
            "actor_role": "OPERATIONS_MANAGER",
            "reason": "Restore after E2E kill-switch probe",
        },
    )
    _require(
        status == 200 and isinstance(restored, dict) and restored["active"] is False,
        "kill switch off failed",
    )

    console_ok = _console_reachable(console_url)
    evidence = {
        "decision_id": decision_id,
        "order_id": f"order-e2e-{suffix}",
        "action": decision["recommendation"]["selected_action"],
        "execution_status": approved["execution"]["status"],
        "verification_status": verified["outcome"]["status"],
        "console_reachable": console_ok,
        "tenant_id": tenant_id,
    }
    STATE_PATH.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"result": "PASSED", **evidence}, indent=2, sort_keys=True))
    return evidence


def _run_replay(api_url: str) -> None:
    if not STATE_PATH.exists():
        raise SystemExit(f"missing replay state at {STATE_PATH}")
    evidence = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    status, state = _request("GET", f"{api_url}/v1/decisions/{evidence['decision_id']}")
    _require(status == 200 and isinstance(state, dict), f"replay fetch failed: {status} {state}")
    _require(
        state["decision"]["decision_id"] == evidence["decision_id"],
        "decision lost after restart",
    )
    _require(state["execution"]["status"] == "SUCCEEDED", "execution evidence lost after restart")
    _require(state["outcome"]["status"] == "VERIFIED", "outcome evidence lost after restart")
    print(json.dumps({"result": "REPLAY_PASSED", "decision_id": evidence["decision_id"]}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="PromiseGuard local stack end-to-end probe")
    parser.add_argument("--api-url", default=DEFAULT_API)
    parser.add_argument("--console-url", default=DEFAULT_CONSOLE)
    parser.add_argument("--wait-seconds", type=int, default=60)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    ready = _wait_for_api(args.api_url, args.wait_seconds)
    print(json.dumps({"ready": ready}, indent=2, sort_keys=True))
    if args.replay:
        _run_replay(args.api_url)
        return
    _run_fresh(args.api_url, args.console_url)


if __name__ == "__main__":
    main()
