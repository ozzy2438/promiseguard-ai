"""Add hard application budget accounting and structured OpenAI run evidence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_openai_budget_and_runs"
down_revision: str | None = "0002_autonomy_controls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "openai_budgets",
        sa.Column("budget_key", sa.String(length=80), nullable=False),
        sa.Column("limit_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("reserved_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("spent_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("budget_key"),
    )
    op.create_table(
        "openai_runs",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("request_key", sa.String(length=64), nullable=False),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_version", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("context_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("reserved_cost_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("actual_cost_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("response_id", sa.String(length=160), nullable=True),
        sa.Column("review", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reservation_expires_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("error_code", sa.String(length=160), nullable=True),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["decision_id"], ["decisions.decision_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        "ix_openai_runs_request_status",
        "openai_runs",
        ["request_key", "status"],
    )
    op.create_index(
        "ix_openai_runs_decision_created",
        "openai_runs",
        ["decision_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_openai_runs_decision_created", table_name="openai_runs")
    op.drop_index("ix_openai_runs_request_status", table_name="openai_runs")
    op.drop_table("openai_runs")
    op.drop_table("openai_budgets")
