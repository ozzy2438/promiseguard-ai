"""Add persistent kill-switch, autonomy profiles and evidence."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_autonomy_controls"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_controls",
        sa.Column("control_key", sa.String(length=80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.String(length=120), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("control_key"),
    )
    op.create_table(
        "autonomy_profiles",
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("level", sa.String(length=40), nullable=False),
        sa.Column("verified_successes", sa.Integer(), nullable=False),
        sa.Column("consecutive_verified_successes", sa.Integer(), nullable=False),
        sa.Column("compensation_count", sa.Integer(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("last_evidence_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.String(length=120), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("action"),
    )
    op.create_table(
        "autonomy_evidence",
        sa.Column("evidence_id", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("evidence_kind", sa.String(length=40), nullable=False),
        sa.Column("successful", sa.Boolean(), nullable=False),
        sa.Column("compensated", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["action"],
            ["autonomy_profiles.action"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("evidence_id"),
    )
    op.create_index(
        "ix_autonomy_evidence_action",
        "autonomy_evidence",
        ["action"],
    )


def downgrade() -> None:
    op.drop_index("ix_autonomy_evidence_action", table_name="autonomy_evidence")
    op.drop_table("autonomy_evidence")
    op.drop_table("autonomy_profiles")
    op.drop_table("runtime_controls")
