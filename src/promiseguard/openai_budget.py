"""Persistent application-level budget guard for OpenAI calls."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from promiseguard.database import Database
from promiseguard.db_models import OpenAIBudgetRow, OpenAIRunRow
from promiseguard.openai_models import (
    AgentBudgetState,
    AgentDecisionReview,
    AgentRunRecord,
    AgentRunStatus,
    AgentTokenUsage,
)
from promiseguard.persistence import ensure_utc


class OpenAIBudgetError(RuntimeError):
    """Base class for local OpenAI budget enforcement errors."""


class OpenAIBudgetExceededError(OpenAIBudgetError):
    """Raised before a call when the application budget is exhausted."""


class OpenAIPerRunLimitError(OpenAIBudgetError):
    """Raised before a call when the conservative reservation is too large."""


class OpenAIBudgetConfigurationError(OpenAIBudgetError):
    """Raised when configured budget is below already committed cost."""


class OpenAIRunNotFoundError(LookupError):
    """Raised when a requested OpenAI run record does not exist."""


class OpenAIBudgetManager:
    budget_key = "promiseguard-openai"

    def __init__(
        self,
        database: Database,
        *,
        limit_usd: Decimal,
        per_run_limit_usd: Decimal,
        reservation_ttl: timedelta = timedelta(minutes=10),
    ) -> None:
        if limit_usd <= 0 or per_run_limit_usd <= 0:
            raise ValueError("OpenAI budget limits must be positive")
        if per_run_limit_usd > limit_usd:
            raise ValueError("per-run limit cannot exceed the project budget")
        self.database = database
        self.limit_usd = limit_usd
        self.per_run_limit_usd = per_run_limit_usd
        self.reservation_ttl = reservation_ttl

    def reserve(
        self,
        *,
        decision_id: str,
        model: str,
        prompt_version: str,
        context_fingerprint: str,
        estimated_cost_usd: Decimal,
        now: datetime | None = None,
    ) -> tuple[AgentRunRecord, bool]:
        timestamp = now or datetime.now(UTC)
        request_key = self._request_key(
            decision_id=decision_id,
            model=model,
            prompt_version=prompt_version,
            context_fingerprint=context_fingerprint,
        )
        with self.database.session() as session:
            existing = session.scalar(
                select(OpenAIRunRow)
                .where(
                    OpenAIRunRow.request_key == request_key,
                    OpenAIRunRow.status == AgentRunStatus.COMPLETED.value,
                )
                .order_by(OpenAIRunRow.created_at.desc())
            )
            if existing is not None:
                return self._to_model(existing), True
            if estimated_cost_usd > self.per_run_limit_usd:
                raise OpenAIPerRunLimitError(
                    "conservative OpenAI run estimate exceeds the configured per-run cap"
                )

            budget = self._locked_budget(session, timestamp)
            self._reclaim_stale(session, budget, timestamp)
            committed = Decimal(budget.spent_usd) + Decimal(budget.reserved_usd)
            if committed + estimated_cost_usd > Decimal(budget.limit_usd):
                raise OpenAIBudgetExceededError(
                    "OpenAI application budget would be exceeded before the request"
                )
            attempt = (
                int(
                    session.scalar(
                        select(func.count(OpenAIRunRow.run_id)).where(
                            OpenAIRunRow.request_key == request_key
                        )
                    )
                    or 0
                )
                + 1
            )
            run_id = self._run_id(request_key, attempt)
            row = OpenAIRunRow(
                run_id=run_id,
                request_key=request_key,
                decision_id=decision_id,
                model=model,
                prompt_version=prompt_version,
                status=AgentRunStatus.RESERVED.value,
                context_fingerprint=context_fingerprint,
                reserved_cost_usd=estimated_cost_usd,
                actual_cost_usd=Decimal("0"),
                input_tokens=None,
                cached_input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                response_id=None,
                review=None,
                created_at=timestamp,
                completed_at=None,
                reservation_expires_at=timestamp + self.reservation_ttl,
                error_code=None,
                validation_errors=[],
            )
            session.add(row)
            budget.reserved_usd = Decimal(budget.reserved_usd) + estimated_cost_usd
            budget.updated_at = timestamp
            budget.version += 1
            session.flush()
            return self._to_model(row), False

    def complete(
        self,
        run_id: str,
        *,
        usage: AgentTokenUsage,
        actual_cost_usd: Decimal,
        response_id: str,
        review: AgentDecisionReview,
        now: datetime | None = None,
    ) -> AgentRunRecord:
        return self._finalise(
            run_id,
            status=AgentRunStatus.COMPLETED,
            usage=usage,
            actual_cost_usd=actual_cost_usd,
            response_id=response_id,
            review=review,
            error_code=None,
            validation_errors=(),
            now=now,
        )

    def reject(
        self,
        run_id: str,
        *,
        usage: AgentTokenUsage,
        actual_cost_usd: Decimal,
        response_id: str,
        error_code: str,
        validation_errors: tuple[str, ...],
        now: datetime | None = None,
    ) -> AgentRunRecord:
        return self._finalise(
            run_id,
            status=AgentRunStatus.REJECTED,
            usage=usage,
            actual_cost_usd=actual_cost_usd,
            response_id=response_id,
            review=None,
            error_code=error_code,
            validation_errors=validation_errors,
            now=now,
        )

    def fail(
        self,
        run_id: str,
        *,
        error_code: str,
        actual_cost_usd: Decimal = Decimal("0"),
        now: datetime | None = None,
    ) -> AgentRunRecord:
        return self._finalise(
            run_id,
            status=AgentRunStatus.FAILED,
            usage=None,
            actual_cost_usd=actual_cost_usd,
            response_id=None,
            review=None,
            error_code=error_code,
            validation_errors=(),
            now=now,
        )

    def get(self, run_id: str) -> AgentRunRecord | None:
        with self.database.session() as session:
            row = session.get(OpenAIRunRow, run_id)
            return None if row is None else self._to_model(row)

    def state(self, *, now: datetime | None = None) -> AgentBudgetState:
        timestamp = now or datetime.now(UTC)
        with self.database.session() as session:
            budget = self._locked_budget(session, timestamp)
            self._reclaim_stale(session, budget, timestamp)
            return self._budget_model(budget)

    def _finalise(
        self,
        run_id: str,
        *,
        status: AgentRunStatus,
        usage: AgentTokenUsage | None,
        actual_cost_usd: Decimal,
        response_id: str | None,
        review: AgentDecisionReview | None,
        error_code: str | None,
        validation_errors: tuple[str, ...],
        now: datetime | None,
    ) -> AgentRunRecord:
        if actual_cost_usd < 0:
            raise ValueError("actual OpenAI cost cannot be negative")
        timestamp = now or datetime.now(UTC)
        with self.database.session() as session:
            row = session.get(OpenAIRunRow, run_id)
            if row is None:
                raise OpenAIRunNotFoundError(run_id)
            if row.status != AgentRunStatus.RESERVED.value:
                return self._to_model(row)
            budget = self._locked_budget(session, timestamp)
            budget.reserved_usd = max(
                Decimal("0"),
                Decimal(budget.reserved_usd) - Decimal(row.reserved_cost_usd),
            )
            budget.spent_usd = Decimal(budget.spent_usd) + actual_cost_usd
            budget.updated_at = timestamp
            budget.version += 1
            row.status = status.value
            row.actual_cost_usd = actual_cost_usd
            row.response_id = response_id
            row.review = None if review is None else review.model_dump(mode="json")
            row.completed_at = timestamp
            row.error_code = error_code
            row.validation_errors = list(validation_errors)
            if usage is not None:
                row.input_tokens = usage.input_tokens
                row.cached_input_tokens = usage.cached_input_tokens
                row.output_tokens = usage.output_tokens
                row.total_tokens = usage.total_tokens
            session.flush()
            return self._to_model(row)

    def _locked_budget(self, session: Session, timestamp: datetime) -> OpenAIBudgetRow:
        row = session.scalar(
            select(OpenAIBudgetRow)
            .where(OpenAIBudgetRow.budget_key == self.budget_key)
            .with_for_update()
        )
        if row is None:
            row = OpenAIBudgetRow(
                budget_key=self.budget_key,
                limit_usd=self.limit_usd,
                reserved_usd=Decimal("0"),
                spent_usd=Decimal("0"),
                updated_at=timestamp,
                version=1,
            )
            session.add(row)
            session.flush()
            return row
        committed = Decimal(row.spent_usd) + Decimal(row.reserved_usd)
        if self.limit_usd < committed:
            raise OpenAIBudgetConfigurationError(
                "configured OpenAI budget is below already spent or reserved cost"
            )
        if Decimal(row.limit_usd) != self.limit_usd:
            row.limit_usd = self.limit_usd
            row.updated_at = timestamp
            row.version += 1
            session.flush()
        return row

    @staticmethod
    def _reclaim_stale(session: Session, budget: OpenAIBudgetRow, now: datetime) -> None:
        stale = session.scalars(
            select(OpenAIRunRow).where(
                OpenAIRunRow.status == AgentRunStatus.RESERVED.value,
                OpenAIRunRow.reservation_expires_at < now,
            )
        ).all()
        for row in stale:
            reserved = Decimal(row.reserved_cost_usd)
            budget.reserved_usd = max(
                Decimal("0"),
                Decimal(budget.reserved_usd) - reserved,
            )
            budget.spent_usd = Decimal(budget.spent_usd) + reserved
            row.status = AgentRunStatus.FAILED.value
            row.actual_cost_usd = reserved
            row.error_code = "STALE_RESERVATION_CHARGED_CONSERVATIVELY"
            row.completed_at = now
        if stale:
            budget.updated_at = now
            budget.version += 1
            session.flush()

    @staticmethod
    def _request_key(
        *, decision_id: str, model: str, prompt_version: str, context_fingerprint: str
    ) -> str:
        value = "|".join((decision_id, model, prompt_version, context_fingerprint))
        return sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _run_id(request_key: str, attempt: int) -> str:
        return f"llm_{sha256(f'{request_key}|{attempt}'.encode()).hexdigest()[:24]}"

    @staticmethod
    def _to_model(row: OpenAIRunRow) -> AgentRunRecord:
        usage = None
        if row.input_tokens is not None:
            usage = AgentTokenUsage(
                input_tokens=row.input_tokens,
                cached_input_tokens=row.cached_input_tokens or 0,
                output_tokens=row.output_tokens or 0,
                total_tokens=row.total_tokens or 0,
            )
        created_at = ensure_utc(row.created_at)
        if created_at is None:
            raise ValueError("persisted OpenAI run is missing created_at")
        return AgentRunRecord.model_validate(
            {
                "run_id": row.run_id,
                "request_key": row.request_key,
                "decision_id": row.decision_id,
                "model": row.model,
                "prompt_version": row.prompt_version,
                "status": row.status,
                "context_fingerprint": row.context_fingerprint,
                "reserved_cost_usd": row.reserved_cost_usd,
                "actual_cost_usd": row.actual_cost_usd,
                "usage": usage,
                "response_id": row.response_id,
                "review": row.review,
                "created_at": created_at,
                "completed_at": ensure_utc(row.completed_at),
                "error_code": row.error_code,
                "validation_errors": tuple(row.validation_errors or []),
            }
        )

    @staticmethod
    def _budget_model(row: OpenAIBudgetRow) -> AgentBudgetState:
        updated_at = ensure_utc(row.updated_at)
        if updated_at is None:
            raise ValueError("persisted OpenAI budget is missing updated_at")
        remaining = max(
            Decimal("0"),
            Decimal(row.limit_usd) - Decimal(row.spent_usd) - Decimal(row.reserved_usd),
        )
        return AgentBudgetState(
            budget_key=row.budget_key,
            limit_usd=row.limit_usd,
            reserved_usd=row.reserved_usd,
            spent_usd=row.spent_usd,
            remaining_usd=remaining,
            updated_at=updated_at,
            version=row.version,
        )
