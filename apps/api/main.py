"""FastAPI entry point for the PromiseGuard shadow-evaluation slice."""

from fastapi import FastAPI

from promiseguard.models import DecisionTrace, EvaluationRequest
from promiseguard.orchestrator import PromiseGuardOrchestrator

app = FastAPI(
    title="PromiseGuard AI",
    version="0.1.0",
    description="Shadow-mode order recovery decision API.",
)
orchestrator = PromiseGuardOrchestrator()


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/shadow/evaluate", response_model=DecisionTrace)
def evaluate_shadow(request: EvaluationRequest) -> DecisionTrace:
    return orchestrator.evaluate(request)
