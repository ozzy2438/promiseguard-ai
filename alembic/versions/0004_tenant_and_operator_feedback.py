"""Add tenant isolation on decisions and operator feedback evidence."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_tenant_feedback"
down_revision: str | None = "0003_openai_budget_and_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    decision_columns = {column["name"] for column in inspector.get_columns("decisions")}
    decision_indexes = {index["name"] for index in inspector.get_indexes("decisions")}
    tables = set(inspector.get_table_names())

    if "tenant_id" not in decision_columns:
        op.add_column(
            "decisions",
            sa.Column(
                "tenant_id",
                sa.String(length=80),
                nullable=False,
                server_default="local-default",
            ),
        )
    if "ix_decisions_tenant_id" not in decision_indexes:
        op.create_index("ix_decisions_tenant_id", "decisions", ["tenant_id"])
    if "operator_feedback" not in tables:
        op.create_table(
            "operator_feedback",
            sa.Column("feedback_id", sa.String(length=64), nullable=False),
            sa.Column("decision_id", sa.String(length=64), nullable=False),
            sa.Column("actor_id", sa.String(length=120), nullable=False),
            sa.Column("actor_role", sa.String(length=40), nullable=False),
            sa.Column("useful", sa.Boolean(), nullable=False),
            sa.Column("expected_outcome_matched", sa.Boolean(), nullable=True),
            sa.Column("comment", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["decision_id"], ["decisions.decision_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("feedback_id"),
        )
        op.create_index("ix_operator_feedback_decision_id", "operator_feedback", ["decision_id"])
        op.create_index(
            "ix_operator_feedback_decision_created",
            "operator_feedback",
            ["decision_id", "created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "operator_feedback" in tables:
        op.drop_index("ix_operator_feedback_decision_created", table_name="operator_feedback")
        op.drop_index("ix_operator_feedback_decision_id", table_name="operator_feedback")
        op.drop_table("operator_feedback")
    decision_indexes = {index["name"] for index in inspector.get_indexes("decisions")}
    decision_columns = {column["name"] for column in inspector.get_columns("decisions")}
    if "ix_decisions_tenant_id" in decision_indexes:
        op.drop_index("ix_decisions_tenant_id", table_name="decisions")
    if "tenant_id" in decision_columns:
        op.drop_column("decisions", "tenant_id")
