"""Application service for approval, execution, verification and recovery."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256

from promiseguard.approval import ApprovalError, ApprovalService
from promiseguard.database import Database
from promiseguard.execution import ActionGateway
from promiseguard.ledger import DecisionLedger
from promiseguard.models import (
    ActionCommand,
    ApprovalDecisionInput,
    ApprovalStatus,
    DecisionTrace,
    DeliveryObservation,
    EvaluationRequest,
    PolicyDisposition,
    RecoveryAction,
    UserRole,
    WorkflowState,
)
from promiseguard.persistence import EventRepository, RecordNotFoundError
from promiseguard.verification import OutcomeVerificationService


class WorkflowError(RuntimeError):
    """Raised when a workflow transition is invalid or unsupported."""


class RecoveryWorkflowService:
    """Coordinate immutable decisions with approval and governed execution."""

    def __init__(
        self,
        *,
        database: Database,
        ledger: DecisionLedger,
        approvals: ApprovalService,
        actions: ActionGateway,
        verification: OutcomeVerificationService,
    ) -> None:
        self.database = database
        self.ledger = ledger
        self.approvals = approvals
        self.actions = actions
        self.verification = verification
        self.events = EventRepository()

    def submit(
        self,
        decision_id: str,
        *,
        actor_id: str,
        now: datetime | None = None,
    ) -> WorkflowState:
        decision = self._decision(decision_id)
        if decision.policy.disposition in {
            PolicyDisposition.BLOCK,
            PolicyDisposition.ESCALATE,
            PolicyDisposition.TAKE_NO_ACTION,
        }:
            return WorkflowState(decision=decision)

        if decision.policy.disposition is PolicyDisposition.AUTO_EXECUTE:
            request = self._request(decision.event_id)
            command = self._command_for_decision(
                decision_id=decision_id,
                request=request,
                actor_id=actor_id,
                approved_by=None,
            )
            execution = self.actions.execute(command, request.order, now=now)
            return WorkflowState(decision=decision, execution=execution)

        approval = self.approvals.request(
            decision,
            requested_by=actor_id,
            now=now,
        )
        return WorkflowState(decision=decision, approval=approval)

    def approve_and_execute(
        self,
        approval_id: str,
        approval_input: ApprovalDecisionInput,
        *,
        now: datetime | None = None,
    ) -> WorkflowState:
        pending = self.approvals.get(approval_id)
        if pending is None:
            raise RecordNotFoundError(f"approval {approval_id!r} not found")
        decision = self._decision(pending.decision_id)
        if pending.requested_action is not decision.recommendation.selected_action:
            raise WorkflowError("approval action no longer matches the immutable decision")
        request = self._request(decision.event_id)
        self._assert_approval_authority(approval_input, decision, request)

        approval = self.approvals.approve(approval_id, approval_input, now=now)
        if approval.status is not ApprovalStatus.APPROVED:
            raise WorkflowError("approval did not reach APPROVED state")
        command = self._command_for_decision(
            decision_id=decision.decision_id,
            request=request,
            actor_id=approval.requested_by,
            approved_by=approval.decided_by,
        )
        execution = self.actions.execute(command, request.order, now=now)
        return WorkflowState(
            decision=decision,
            approval=approval,
            execution=execution,
        )

    def reject(
        self,
        approval_id: str,
        approval_input: ApprovalDecisionInput,
        *,
        now: datetime | None = None,
    ) -> WorkflowState:
        approval = self.approvals.reject(approval_id, approval_input, now=now)
        return WorkflowState(
            decision=self._decision(approval.decision_id),
            approval=approval,
        )

    def verify(
        self,
        decision_id: str,
        *,
        observation: DeliveryObservation | None = None,
        now: datetime | None = None,
    ) -> WorkflowState:
        decision = self._decision(decision_id)
        execution = self.actions.get_by_decision(decision_id)
        if execution is None:
            raise RecordNotFoundError("decision has no executed action")
        request = self._request(decision.event_id)
        outcome = self.verification.verify(
            decision=decision,
            execution=execution,
            order=request.order,
            observation=observation,
            now=now,
        )
        return WorkflowState(
            decision=decision,
            execution=execution,
            outcome=outcome,
        )

    def get_state(self, decision_id: str) -> WorkflowState:
        decision = self._decision(decision_id)
        execution = self.actions.get_by_decision(decision_id)
        outcome = self.verification.get_by_decision(decision_id)
        with self.database.session() as session:
            approval = self.approvals.repository.get_by_decision(session, decision_id)
        return WorkflowState(
            decision=decision,
            approval=approval,
            execution=execution,
            outcome=outcome,
        )

    def _decision(self, decision_id: str) -> DecisionTrace:
        decision = self.ledger.get(decision_id)
        if decision is None:
            raise RecordNotFoundError(f"decision {decision_id!r} not found")
        return decision

    def _request(self, event_id: str) -> EvaluationRequest:
        with self.database.session() as session:
            payload = self.events.get_request_payload(session, event_id=event_id)
        if payload is None:
            raise RecordNotFoundError(f"event {event_id!r} not found")
        return EvaluationRequest.model_validate(payload)

    def _assert_approval_authority(
        self,
        approval_input: ApprovalDecisionInput,
        decision: DecisionTrace,
        request: EvaluationRequest,
    ) -> None:
        if approval_input.actor_role is not UserRole.OPERATIONS_ANALYST:
            return
        selected = next(
            option
            for option in decision.recommendation.ranked_options
            if option.action is decision.recommendation.selected_action
        )
        if request.order.restricted_product:
            raise ApprovalError("restricted products require operations-manager approval")
        if selected.intervention_cost > Decimal("20.00"):
            raise ApprovalError(
                "intervention exceeds the operations-analyst delegated cost limit"
            )

    def _command_for_decision(
        self,
        *,
        decision_id: str,
        request: EvaluationRequest,
        actor_id: str,
        approved_by: str | None,
    ) -> ActionCommand:
        decision = self._decision(decision_id)
        action = decision.recommendation.selected_action
        selected = next(
            option for option in decision.recommendation.ranked_options if option.action is action
        )
        idempotency_material = "|".join(
            (
                decision.decision_id,
                action.value,
                decision.policy.policy_version,
            )
        )
        parameters: dict[str, object]
        if action is RecoveryAction.REROUTE:
            parameters = {
                "from_location": request.order.current_fulfilment_location,
                "to_location": request.order.alternative_location_id,
                "sku": request.order.sku,
                "quantity": request.order.quantity,
            }
        elif action is RecoveryAction.CARRIER_UPGRADE:
            parameters = {
                "from_service": request.order.current_carrier_service,
                "to_service": request.order.upgraded_carrier_service,
            }
        elif action is RecoveryAction.SPLIT_SHIPMENT:
            parameters = {"split": True, "quantity": request.order.quantity}
        else:
            raise WorkflowError(f"action {action.value} is not executable")
        return ActionCommand(
            decision_id=decision.decision_id,
            order_id=request.order.order_id,
            action=action,
            idempotency_key=f"pg:{sha256(idempotency_material.encode()).hexdigest()[:32]}",
            requested_by=actor_id,
            approved_by=approved_by,
            expected_intervention_cost=Decimal(selected.intervention_cost),
            parameters=parameters,
        )
