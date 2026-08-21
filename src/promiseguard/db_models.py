"""Relational persistence schema for decisions, controls, OpenAI runs and outcomes."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from promiseguard.database import Base


class OperationalEventRow(Base):
    __tablename__ = "operational_events"
    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "event_id",
            "event_version",
            name="uq_operational_event_identity",
        ),
        Index("ix_operational_events_dedup_key", "deduplication_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    event_id: Mapped[str] = mapped_column(String(120), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingestion_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(180), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DecisionRow(Base):
    __tablename__ = "decisions"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(
        String(80), nullable=False, default="local-default", index=True
    )
    trace: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApprovalRow(Base):
    __tablename__ = "approvals"
    __table_args__ = (Index("ix_approvals_status_requested_at", "status", "requested_at"),)

    approval_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decisions.decision_id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_action: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(120), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(120))
    decided_by_role: Mapped[str | None] = mapped_column(String(40))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActionRow(Base):
    __tablename__ = "actions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_actions_idempotency_key"),
        Index("ix_actions_status_started_at", "status", "started_at"),
    )

    action_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decisions.decision_id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    command: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(120))
    manual_recovery_reason: Mapped[str | None] = mapped_column(Text)


class OutcomeRow(Base):
    __tablename__ = "outcomes"
    __table_args__ = (UniqueConstraint("decision_id", name="uq_outcomes_decision_id"),)

    outcome_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decisions.decision_id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_id: Mapped[str] = mapped_column(
        ForeignKey("actions.action_id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    on_time_delivery_observed: Mapped[bool | None]
    actual_intervention_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    realised_gross_margin: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    estimated_incremental_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    evidence_references: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class RuntimeControlRow(Base):
    __tablename__ = "runtime_controls"

    control_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(120), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)


class AutonomyProfileRow(Base):
    __tablename__ = "autonomy_profiles"

    action: Mapped[str] = mapped_column(String(40), primary_key=True)
    level: Mapped[str] = mapped_column(String(40), nullable=False)
    verified_successes: Mapped[int] = mapped_column(Integer, nullable=False)
    consecutive_verified_successes: Mapped[int] = mapped_column(Integer, nullable=False)
    compensation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    last_evidence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[str] = mapped_column(String(120), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)


class AutonomyEvidenceRow(Base):
    __tablename__ = "autonomy_evidence"

    evidence_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    action: Mapped[str] = mapped_column(
        ForeignKey("autonomy_profiles.action", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    successful: Mapped[bool] = mapped_column(Boolean, nullable=False)
    compensated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OpenAIBudgetRow(Base):
    __tablename__ = "openai_budgets"

    budget_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    limit_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    spent_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)


class OpenAIRunRow(Base):
    __tablename__ = "openai_runs"
    __table_args__ = (
        Index("ix_openai_runs_request_status", "request_key", "status"),
        Index("ix_openai_runs_decision_created", "decision_id", "created_at"),
    )

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_key: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decisions.decision_id", ondelete="CASCADE"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    context_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    reserved_cost_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    actual_cost_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    response_id: Mapped[str | None] = mapped_column(String(160))
    review: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reservation_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(String(160))
    validation_errors: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class OperatorFeedbackRow(Base):
    __tablename__ = "operator_feedback"
    __table_args__ = (Index("ix_operator_feedback_decision_created", "decision_id", "created_at"),)

    feedback_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decisions.decision_id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(40), nullable=False)
    useful: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expected_outcome_matched: Mapped[bool | None]
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
