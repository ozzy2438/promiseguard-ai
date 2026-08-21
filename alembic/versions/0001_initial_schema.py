"""Create durable PromiseGuard evidence tables."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operational_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column("event_id", sa.String(length=120), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingestion_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(length=20), nullable=False),
        sa.Column("deduplication_key", sa.String(length=180), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_system", "event_id", "event_version", name="uq_operational_event_identity"
        ),
    )
    op.create_index(
        "ix_operational_events_dedup_key",
        "operational_events",
        ["deduplication_key"],
    )
    op.create_table(
        "decisions",
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("event_id", sa.String(length=120), nullable=False),
        sa.Column("order_id", sa.String(length=120), nullable=False),
        sa.Column("trace", sa.JSON(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("decision_id"),
    )
    op.create_index("ix_decisions_event_id", "decisions", ["event_id"])
    op.create_index("ix_decisions_order_id", "decisions", ["order_id"])
    op.create_table(
        "approvals",
        sa.Column("approval_id", sa.String(length=64), nullable=False),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("requested_action", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("requested_by", sa.String(length=120), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.String(length=120), nullable=True),
        sa.Column("decided_by_role", sa.String(length=40), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.decision_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("approval_id"),
    )
    op.create_index("ix_approvals_decision_id", "approvals", ["decision_id"])
    op.create_index("ix_approvals_status_requested_at", "approvals", ["status", "requested_at"])
    op.create_table(
        "actions",
        sa.Column("action_id", sa.String(length=64), nullable=False),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("command", sa.JSON(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("manual_recovery_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.decision_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("action_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_actions_idempotency_key"),
    )
    op.create_index("ix_actions_decision_id", "actions", ["decision_id"])
    op.create_index("ix_actions_order_id", "actions", ["order_id"])
    op.create_index("ix_actions_status_started_at", "actions", ["status", "started_at"])
    op.create_table(
        "outcomes",
        sa.Column("outcome_id", sa.String(length=64), nullable=False),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("action_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("on_time_delivery_observed", sa.Boolean(), nullable=True),
        sa.Column("actual_intervention_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("realised_gross_margin", sa.Numeric(14, 2), nullable=False),
        sa.Column("estimated_incremental_value", sa.Numeric(14, 2), nullable=False),
        sa.Column("evidence_references", sa.JSON(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["action_id"], ["actions.action_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.decision_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("outcome_id"),
        sa.UniqueConstraint("decision_id", name="uq_outcomes_decision_id"),
    )
    op.create_index("ix_outcomes_action_id", "outcomes", ["action_id"])
    op.create_index("ix_outcomes_decision_id", "outcomes", ["decision_id"])


def downgrade() -> None:
    op.drop_index("ix_outcomes_decision_id", table_name="outcomes")
    op.drop_index("ix_outcomes_action_id", table_name="outcomes")
    op.drop_table("outcomes")
    op.drop_index("ix_actions_status_started_at", table_name="actions")
    op.drop_index("ix_actions_order_id", table_name="actions")
    op.drop_index("ix_actions_decision_id", table_name="actions")
    op.drop_table("actions")
    op.drop_index("ix_approvals_status_requested_at", table_name="approvals")
    op.drop_index("ix_approvals_decision_id", table_name="approvals")
    op.drop_table("approvals")
    op.drop_index("ix_decisions_order_id", table_name="decisions")
    op.drop_index("ix_decisions_event_id", table_name="decisions")
    op.drop_table("decisions")
    op.drop_index("ix_operational_events_dedup_key", table_name="operational_events")
    op.drop_table("operational_events")
