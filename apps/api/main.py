"""FastAPI application for persistent PromiseGuard decision and action workflows."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from promiseguard.approval import ApprovalError
from promiseguard.autonomy import AutonomyControlError
from promiseguard.config import Settings
from promiseguard.execution import ActionExecutionError
from promiseguard.models import (
    ActionExecution,
    ApprovalDecisionInput,
    ApprovalRecord,
    AutonomyProfile,
    AutonomyUpdateInput,
    DecisionTrace,
    DeliveryObservation,
    EvaluationRequest,
    KillSwitchState,
    KillSwitchUpdateInput,
    OperatingMode,
    RecoveryAction,
    SubmitDecisionInput,
    WorkflowState,
)
from promiseguard.observability import (
    bind_correlation_id,
    configure_json_logging,
    normalise_correlation_id,
    reset_correlation_id,
)
from promiseguard.persistence import PersistenceConflictError, RecordNotFoundError
from promiseguard.services import ServiceContainer
from promiseguard.workflow import WorkflowError


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_json_logging()
    logger = logging.getLogger("promiseguard.api")
    services = ServiceContainer.build(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        services.close()

    app = FastAPI(
        title="PromiseGuard AI",
        version="0.3.0",
        description="Persistent, policy-governed fulfilment recovery reference API.",
        lifespan=lifespan,
    )
    app.state.services = services

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        correlation_id = normalise_correlation_id(
            request.headers.get("X-Correlation-ID")
        )
        token = bind_correlation_id(correlation_id)
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_seconds": perf_counter() - started,
                },
            )
            raise
        else:
            response.headers["X-Correlation-ID"] = correlation_id
            logger.info(
                "request_completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_seconds": perf_counter() - started,
                },
            )
            return response
        finally:
            reset_correlation_id(token)

    @app.exception_handler(RecordNotFoundError)
    async def not_found_handler(_, exc: RecordNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", str(exc))

    @app.exception_handler(PersistenceConflictError)
    async def conflict_handler(_, exc: PersistenceConflictError):
        return _error(status.HTTP_409_CONFLICT, "PERSISTENCE_CONFLICT", str(exc))

    @app.exception_handler(ApprovalError)
    async def approval_handler(_, exc: ApprovalError):
        return _error(status.HTTP_409_CONFLICT, "APPROVAL_ERROR", str(exc))

    @app.exception_handler(ActionExecutionError)
    async def action_handler(_, exc: ActionExecutionError):
        return _error(status.HTTP_409_CONFLICT, "ACTION_EXECUTION_ERROR", str(exc))

    @app.exception_handler(AutonomyControlError)
    async def autonomy_handler(_, exc: AutonomyControlError):
        return _error(status.HTTP_409_CONFLICT, "AUTONOMY_CONTROL_ERROR", str(exc))

    @app.exception_handler(WorkflowError)
    async def workflow_handler(_, exc: WorkflowError):
        return _error(status.HTTP_409_CONFLICT, "WORKFLOW_ERROR", str(exc))

    @app.get("/healthz")
    def health() -> dict[str, str]:
        with services.database.session() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/readyz")
    def readiness() -> dict[str, str]:
        with services.database.session() as session:
            session.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "environment": services.settings.environment,
            "scorer": services.orchestrator.scorer.model_version,
            "kill_switch": str(services.autonomy.kill_switch().active).lower(),
        }

    @app.get("/v1/controls/kill-switch", response_model=KillSwitchState)
    def get_kill_switch() -> KillSwitchState:
        return services.autonomy.kill_switch()

    @app.post("/v1/controls/kill-switch", response_model=KillSwitchState)
    def update_kill_switch(request: KillSwitchUpdateInput) -> KillSwitchState:
        return services.autonomy.set_kill_switch(request)

    @app.get("/v1/autonomy", response_model=tuple[AutonomyProfile, ...])
    def list_autonomy_profiles() -> tuple[AutonomyProfile, ...]:
        return services.autonomy.profiles()

    @app.get("/v1/autonomy/{action}", response_model=AutonomyProfile)
    def get_autonomy_profile(action: RecoveryAction) -> AutonomyProfile:
        return services.autonomy.profile(action)

    @app.post("/v1/autonomy/{action}", response_model=AutonomyProfile)
    def update_autonomy_profile(
        action: RecoveryAction,
        request: AutonomyUpdateInput,
    ) -> AutonomyProfile:
        return services.autonomy.set_profile(action, request)

    @app.post("/v1/evaluate", response_model=DecisionTrace)
    def evaluate(request: EvaluationRequest) -> DecisionTrace:
        started = perf_counter()
        trace = services.evaluation.evaluate(request)
        services.metrics.decision_latency.observe(perf_counter() - started)
        services.metrics.decisions.labels(
            trace.policy.disposition.value,
            trace.mode.value,
        ).inc()
        return trace

    @app.post("/v1/shadow/evaluate", response_model=DecisionTrace)
    def evaluate_shadow(request: EvaluationRequest) -> DecisionTrace:
        shadow = request.model_copy(update={"mode": OperatingMode.SHADOW})
        return evaluate(shadow)

    @app.get("/v1/decisions", response_model=tuple[DecisionTrace, ...])
    def list_decisions(limit: int = 100) -> tuple[DecisionTrace, ...]:
        if limit < 1 or limit > 500:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="limit must be between 1 and 500",
            )
        return services.ledger.list_recent(limit=limit)

    @app.get("/v1/decisions/{decision_id}", response_model=WorkflowState)
    def get_decision(decision_id: str) -> WorkflowState:
        return services.workflow.get_state(decision_id)

    @app.post("/v1/decisions/{decision_id}/submit", response_model=WorkflowState)
    def submit_decision(
        decision_id: str,
        request: SubmitDecisionInput,
    ) -> WorkflowState:
        state = services.workflow.submit(decision_id, actor_id=request.actor_id)
        if state.approval is not None:
            services.metrics.approvals.labels(state.approval.status.value).inc()
        if state.execution is not None:
            services.metrics.actions.labels(
                state.execution.command.action.value,
                state.execution.status.value,
            ).inc()
        return state

    @app.get("/v1/approvals", response_model=tuple[ApprovalRecord, ...])
    def list_pending_approvals() -> tuple[ApprovalRecord, ...]:
        return services.approvals.list_pending()

    @app.post("/v1/approvals/{approval_id}/approve", response_model=WorkflowState)
    def approve(
        approval_id: str,
        request: ApprovalDecisionInput,
    ) -> WorkflowState:
        state = services.workflow.approve_and_execute(approval_id, request)
        if state.approval is not None:
            services.metrics.approvals.labels(state.approval.status.value).inc()
        if state.execution is not None:
            services.metrics.actions.labels(
                state.execution.command.action.value,
                state.execution.status.value,
            ).inc()
        return state

    @app.post("/v1/approvals/{approval_id}/reject", response_model=WorkflowState)
    def reject(
        approval_id: str,
        request: ApprovalDecisionInput,
    ) -> WorkflowState:
        state = services.workflow.reject(approval_id, request)
        if state.approval is not None:
            services.metrics.approvals.labels(state.approval.status.value).inc()
        return state

    @app.get("/v1/actions/{action_id}", response_model=ActionExecution)
    def get_action(action_id: str) -> ActionExecution:
        action = services.actions.get(action_id)
        if action is None:
            raise RecordNotFoundError(f"action {action_id!r} not found")
        return action

    @app.post("/v1/decisions/{decision_id}/verify", response_model=WorkflowState)
    def verify(
        decision_id: str,
        observation: DeliveryObservation,
    ) -> WorkflowState:
        state = services.workflow.verify(decision_id, observation=observation)
        if state.outcome is not None:
            services.metrics.verifications.labels(state.outcome.status.value).inc()
        return state

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(
            content=generate_latest(services.metrics.registry),
            media_type=CONTENT_TYPE_LATEST,
        )

    return app


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": {"code": code, "message": message}},
    )
