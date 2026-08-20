"""Operations console for PromiseGuard decisions, approvals and safety controls."""

from __future__ import annotations

import os
from typing import Any

import httpx
import streamlit as st

API_URL = os.getenv("PROMISEGUARD_API_URL", "http://localhost:8000").rstrip("/")

st.set_page_config(page_title="PromiseGuard AI", layout="wide")
st.title("PromiseGuard AI")
st.caption("Protect the promise before it breaks — operations review console")


def api_get(path: str) -> Any:
    response = httpx.get(f"{API_URL}{path}", timeout=10)
    response.raise_for_status()
    return response.json()


def api_post(path: str, payload: dict[str, Any]) -> Any:
    response = httpx.post(f"{API_URL}{path}", json=payload, timeout=20)
    response.raise_for_status()
    return response.json()


try:
    ready = api_get("/readyz")
    kill_switch = api_get("/v1/controls/kill-switch")
except Exception as exc:
    st.error(f"API unavailable: {exc}")
    st.stop()

st.sidebar.success(f"API ready · scorer {ready['scorer']}")
if kill_switch["active"]:
    st.sidebar.error("Global action kill switch: ACTIVE")
else:
    st.sidebar.info("Global action kill switch: inactive")

page = st.sidebar.radio(
    "View",
    (
        "Decisions",
        "Pending approvals",
        "Decision detail",
        "Autonomy & safety",
    ),
)

if page == "Decisions":
    decisions = api_get("/v1/decisions?limit=100")
    rows = [
        {
            "decision_id": item["decision_id"],
            "order_id": item["order_id"],
            "risk": item["risk"]["failure_probability"],
            "selected_action": item["recommendation"]["selected_action"],
            "incremental_value": item["recommendation"][
                "expected_incremental_value_vs_no_action"
            ],
            "policy": item["policy"]["disposition"],
            "control_version": item["policy"]["control_version"],
            "mode": item["mode"],
            "created_at": item["created_at"],
        }
        for item in decisions
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)

elif page == "Pending approvals":
    approvals = api_get("/v1/approvals")
    if not approvals:
        st.info("No pending approvals.")
    for approval in approvals:
        with st.container(border=True):
            st.subheader(approval["requested_action"])
            st.code(approval["decision_id"])
            st.write(f"Requested by: {approval['requested_by']}")
            st.write(f"Expires: {approval['expires_at']}")
            reason = st.text_input(
                "Approval rationale",
                key=f"reason-{approval['approval_id']}",
                value="Reviewed order evidence and recovery economics",
            )
            left, right = st.columns(2)
            if left.button(
                "Approve and execute",
                key=f"approve-{approval['approval_id']}",
            ):
                result = api_post(
                    f"/v1/approvals/{approval['approval_id']}/approve",
                    {
                        "actor_id": "operations-manager-ui",
                        "actor_role": "OPERATIONS_MANAGER",
                        "reason": reason,
                    },
                )
                st.success(result["execution"]["status"])
                st.rerun()
            if right.button("Reject", key=f"reject-{approval['approval_id']}"):
                api_post(
                    f"/v1/approvals/{approval['approval_id']}/reject",
                    {
                        "actor_id": "operations-manager-ui",
                        "actor_role": "OPERATIONS_MANAGER",
                        "reason": reason,
                    },
                )
                st.warning("Rejected")
                st.rerun()

elif page == "Decision detail":
    decision_id = st.text_input("Decision ID")
    if decision_id:
        state = api_get(f"/v1/decisions/{decision_id}")
        decision = state["decision"]
        st.metric("Promise-failure risk", decision["risk"]["failure_probability"])
        st.metric(
            "Expected incremental value",
            decision["recommendation"]["expected_incremental_value_vs_no_action"],
        )
        st.subheader("Ranked options")
        st.dataframe(
            decision["recommendation"]["ranked_options"],
            use_container_width=True,
        )
        st.subheader("Policy")
        st.json(decision["policy"])
        st.subheader("Approval, execution and outcome")
        st.json(
            {
                "approval": state.get("approval"),
                "execution": state.get("execution"),
                "outcome": state.get("outcome"),
            }
        )

else:
    st.subheader("Global action kill switch")
    st.json(kill_switch)
    control_reason = st.text_input(
        "Control-change reason",
        value="Operations manager safety decision",
    )
    left, right = st.columns(2)
    if left.button("Activate kill switch", disabled=kill_switch["active"]):
        api_post(
            "/v1/controls/kill-switch",
            {
                "active": True,
                "actor_id": "operations-manager-ui",
                "actor_role": "OPERATIONS_MANAGER",
                "reason": control_reason,
            },
        )
        st.rerun()
    if right.button("Deactivate kill switch", disabled=not kill_switch["active"]):
        api_post(
            "/v1/controls/kill-switch",
            {
                "active": False,
                "actor_id": "operations-manager-ui",
                "actor_role": "OPERATIONS_MANAGER",
                "reason": control_reason,
            },
        )
        st.rerun()

    st.subheader("Action autonomy profiles")
    profiles = api_get("/v1/autonomy")
    st.dataframe(profiles, use_container_width=True, hide_index=True)
    st.caption(
        "Bounded autonomy requires the configured number of consecutive verified outcomes. "
        "Any failed or compensated autonomous action resets the evidence streak and suspends "
        "that action profile."
    )
