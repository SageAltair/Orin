from __future__ import annotations

import uuid
import logging
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Response, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from orin_api.auth import get_current_user
from orin_api.ai import AITaskType, AIInterpreter, AIProviderError, IntentName, ModelSelector, create_provider
from orin_api.config import Settings, get_settings
from orin_api.database import get_session
from orin_api.models import (
    Activity,
    ActivityType,
    Capability,
    Command,
    CommandStatus,
    Approval,
    ApprovalStatus,
    Project,
    ProjectStatus,
    Task,
    TaskStatus,
    TaskPriority,
    User,
    UserCapability,
    UserPreferences,
    DeviceStatus,
    WorkerJob,
    WorkerJobStatus,
    WorkerDevice,
)
from orin_api.schemas import (
    ActivityRead,
    CapabilityRead,
    PreferencesRead,
    PreferencesUpdate,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    TaskCreate,
    TaskRead,
    TaskUpdate,
    CommandCreate,
    CommandResult,
    ApprovalDecision,
)
from orin_api.services import (
    add_activity,
    add_project_owner_membership,
    ensure_capability_catalog,
    ensure_user_preferences,
    preference_view,
    require_user,
    update_preferences,
)
from orin_api.rate_limit import consume_user_window
from orin_api.planner import plan_intent
from orin_api.project_context import ProjectContextService
from orin_api.execution import ActionContext, ActionRequest, ActionStatus, ExecutionEngine, ExecutionResult
from orin_api.execution_actions import build_action_registry

router = APIRouter(prefix="/api/v1", tags=["core"])
logger = logging.getLogger(__name__)
ACTION_REGISTRY = build_action_registry()
EXECUTION_ENGINE = ExecutionEngine(ACTION_REGISTRY)


@router.post("/commands", response_model=CommandResult, status_code=status.HTTP_200_OK)
def submit_command(
    data: CommandCreate,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=1, max_length=160),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CommandResult:
    if idempotency_key is not None:
        existing = session.scalar(select(Command).where(Command.user_id == user.id, Command.idempotency_key == idempotency_key))
        if existing is not None:
            if existing.text != data.text:
                raise HTTPException(status_code=409, detail="Idempotency-Key was already used for a different command.")
            return CommandResult(command_id=existing.id, status=existing.status.value,
                intent=existing.response_intent, result=existing.response_json,
                message=existing.response_message or "This command is already being processed.",
                execution=existing.response_execution_json)
    allowance = consume_user_window(session, user_id=user.id, route="command_submit", limit=20)
    response.headers["X-RateLimit-Limit"] = "20"
    response.headers["X-RateLimit-Remaining"] = str(allowance.remaining)
    if not allowance.allowed:
        raise HTTPException(status_code=429, detail={"code": "rate_limited", "message": "Too many commands. Retry after the current minute."},
            headers={"Retry-After": str(allowance.retry_after)})
    command = Command(user_id=user.id, text=data.text, status=CommandStatus.SUBMITTED, idempotency_key=idempotency_key)
    session.add(command)
    try:
        session.flush()
        add_activity(session, user_id=user.id, actor_user_id=user.id,
            activity_type=ActivityType.COMMAND_RECEIVED, summary="Command received",
            command_id=command.id, correlation_id=str(command.id), source="command_api",
            idempotency_key=f"command.received:{command.id}")
        if not settings.ai_provider or not settings.ai_model:
            raise AIProviderError("AI command interpretation is not configured")
        model = ModelSelector(settings.ai_model).select(AITaskType.COMMAND_INTERPRETATION)
        project_context = ProjectContextService(session, user.id).for_command(data.text)
        interpreter = AIInterpreter(create_provider(settings), model)
        proposal = interpreter.interpret(data.text) if project_context is None else interpreter.interpret(
            data.text, context=json.dumps(project_context, ensure_ascii=True, default=str)
        )
        add_activity(session, user_id=user.id, actor_user_id=user.id,
            activity_type=ActivityType.INTENT_INTERPRETED,
            summary=f"Intent interpreted: {proposal.intent.value}", command_id=command.id,
            intent=proposal.intent.value, result_status="interpreted", source="planner",
            correlation_id=str(command.id), idempotency_key=f"command.intent:{command.id}")
        if proposal.intent == IntentName.RESPOND:
            command.status = CommandStatus.COMPLETED
            add_activity(session, user_id=user.id, actor_user_id=user.id,
                activity_type=ActivityType.COMMAND_COMPLETED, summary="Command completed",
                command_id=command.id, result_status="completed", source="command_api",
                correlation_id=str(command.id), idempotency_key=f"command.terminal:{command.id}")
            response = CommandResult(command_id=command.id, status="completed", intent="RESPOND",
                result={"response": proposal.parameters.response}, message=proposal.parameters.response or "Hello! What would you like help with?")
            _cache_command_response(command, response)
            session.commit()
            return response
        if proposal.intent == IntentName.UNSUPPORTED:
            command.status = CommandStatus.FAILED
            add_activity(session, user_id=user.id, actor_user_id=user.id,
                activity_type=ActivityType.COMMAND_FAILED, summary="Command unsupported",
                command_id=command.id, result_status="unsupported", severity="warning",
                source="command_api", correlation_id=str(command.id),
                idempotency_key=f"command.terminal:{command.id}")
            response = CommandResult(command_id=command.id, status="unsupported", intent="UNSUPPORTED", message="This request is not supported.")
            _cache_command_response(command, response)
            session.commit()
            return response
        plan = plan_intent(proposal)
        if plan is None:
            command.status = CommandStatus.FAILED
            add_activity(session, user_id=user.id, actor_user_id=user.id,
                activity_type=ActivityType.COMMAND_FAILED, summary="Command unsupported",
                command_id=command.id, result_status="unsupported", severity="warning",
                source="command_api", correlation_id=str(command.id),
                idempotency_key=f"command.terminal:{command.id}")
            response = CommandResult(command_id=command.id, status="unsupported", intent=proposal.intent.value, message="This request is not supported.")
            _cache_command_response(command, response)
            session.commit()
            return response
        add_activity(session, user_id=user.id, actor_user_id=user.id,
            activity_type=ActivityType.PLAN_CREATED, summary="Validated plan created",
            command_id=command.id, intent=plan.intent.value, result_status="planned",
            source="planner", correlation_id=str(command.id),
            idempotency_key=f"command.plan:{command.id}")
        ensure_user_preferences(session, user)
        autonomy = session.scalar(select(UserPreferences).where(UserPreferences.user_id == user.id))
        result = EXECUTION_ENGINE.execute(ActionRequest(action=plan.action, inputs=plan.inputs),
            ActionContext(session=session, user_id=user.id, command_id=command.id, permissions=_user_action_permissions(session, user.id), command_text=data.text,
                autonomy_mode=autonomy.autonomy_mode if autonomy else "balanced", custom_autonomy=autonomy.custom_autonomy if autonomy else {}))
        return _commit_execution_result(session, command, plan.intent.value, result)
    except AIProviderError as exc:
        session.rollback()
        command.status = CommandStatus.FAILED
        command.idempotency_key = None
        session.add(command)
        session.flush()
        add_activity(session, user_id=user.id, actor_user_id=user.id,
            activity_type=ActivityType.COMMAND_RECEIVED, summary="Command received",
            command_id=command.id, correlation_id=str(command.id), source="command_api",
            idempotency_key=f"command.received:{command.id}")
        add_activity(session, user_id=user.id, actor_user_id=user.id,
            activity_type=ActivityType.COMMAND_FAILED, summary="Command failed during interpretation",
            command_id=command.id, result_status="failed", severity="error", source="command_api",
            correlation_id=str(command.id), idempotency_key=f"command.failed:{command.id}")
        session.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ValueError, ValidationError) as exc:
        session.rollback()
        command.status = CommandStatus.FAILED
        command.idempotency_key = None
        session.add(command)
        session.flush()
        add_activity(session, user_id=user.id, actor_user_id=user.id,
            activity_type=ActivityType.COMMAND_RECEIVED, summary="Command received",
            command_id=command.id, correlation_id=str(command.id), source="command_api",
            idempotency_key=f"command.received:{command.id}")
        add_activity(session, user_id=user.id, actor_user_id=user.id,
            activity_type=ActivityType.COMMAND_FAILED, summary="Command parameters were invalid",
            command_id=command.id, result_status="failed", severity="warning", source="command_api",
            correlation_id=str(command.id), idempotency_key=f"command.failed:{command.id}")
        session.commit()
        raise HTTPException(status_code=422, detail="Command parameters are invalid") from exc
    except HTTPException:
        session.rollback()
        raise
    except SQLAlchemyError as exc:
        session.rollback()
        logger.exception("Database failure while processing command", extra={"user_id": str(user.id)})
        raise HTTPException(status_code=503, detail="Orin could not save this command. Please retry shortly.") from exc


def _user_action_permissions(session: Session, user_id: uuid.UUID) -> frozenset[str]:
    grants = {
        row.code for row in session.execute(
            select(Capability.code).join(UserCapability, UserCapability.capability_id == Capability.id)
            .where(UserCapability.user_id == user_id, UserCapability.granted.is_(True), Capability.is_enabled.is_(True))
        ).all()
    }
    permissions: set[str] = set()
    if "tasks" in grants:
        permissions.update({"task.create", "task.update", "task.complete", "task.read"})
    if "projects" in grants:
        permissions.update({"project.create", "project.read"})
    if "activity" in grants:
        permissions.add("activity.read")
    if "settings" in grants:
        permissions.update({"approval.request", "notification.send", "memory.write", "settings.personalize"})
    if "projects" in grants:
        permissions.add("project.read")
    recent_worker = session.scalar(select(WorkerDevice.id).where(
        WorkerDevice.owner_id == user_id, WorkerDevice.status == DeviceStatus.ACTIVE,
        WorkerDevice.last_seen_at >= datetime.now(timezone.utc) - timedelta(minutes=2),
    ).limit(1))
    if recent_worker is not None:
        permissions.add("worker.execute")
    return frozenset(permissions)


@router.get("/commands/{command_id}", response_model=CommandResult)
def get_command_status(command_id: uuid.UUID, user: User = Depends(get_current_user),
                       session: Session = Depends(get_session)) -> CommandResult:
    command = session.scalar(select(Command).where(Command.id == command_id, Command.user_id == user.id))
    if command is None:
        raise HTTPException(status_code=404, detail="Command not found.")
    status_value = command.status.value
    message = command.response_message or ("This command is awaiting approval." if status_value == "awaiting_approval"
        else "This command failed. Review its activity for details." if status_value == "failed"
        else "This command is still processing.")
    return CommandResult(command_id=command.id, status=status_value, intent=command.response_intent,
        result=command.response_json, message=message, execution=command.response_execution_json)


def _execution_payload(result: ExecutionResult) -> dict[str, object]:
    return {"success": result.success, "action": result.action, "status": result.status.value,
        "result": result.result, "error": result.error, "approval_required": result.approval_required,
        "approval_id": str(result.approval_id) if result.approval_id else None,
        "audit_id": str(result.audit_id) if result.audit_id else None}


def _cache_command_response(command: Command, response: CommandResult) -> None:
    command.response_intent = response.intent
    command.response_json = response.result
    command.response_message = response.message
    command.response_execution_json = response.execution


def _commit_execution_result(session: Session, command: Command, intent: str | None, result: ExecutionResult) -> CommandResult:
    statuses = {ActionStatus.EXECUTED: "completed", ActionStatus.PENDING_APPROVAL: "awaiting_approval",
        ActionStatus.DENIED: "denied", ActionStatus.INVALID: "failed", ActionStatus.FAILED: "failed",
        ActionStatus.UNSUPPORTED: "unsupported"}
    command.status = CommandStatus.AWAITING_APPROVAL if result.status == ActionStatus.PENDING_APPROVAL else (
        CommandStatus.COMPLETED if result.status == ActionStatus.EXECUTED else CommandStatus.FAILED)
    if result.success and isinstance(result.result, dict) and result.result.get("id"):
        entity_id = uuid.UUID(str(result.result["id"]))
        if result.result.get("entity_type") == "task":
            command.task_id = entity_id
        elif result.result.get("entity_type") == "project":
            command.project_id = entity_id
    activity_status = statuses[result.status]
    if result.status != ActionStatus.PENDING_APPROVAL:
        event_type = ActivityType.COMMAND_COMPLETED if result.status == ActionStatus.EXECUTED else ActivityType.COMMAND_FAILED
        add_activity(session, user_id=command.user_id, actor_user_id=command.user_id,
            activity_type=event_type, summary="Command completed" if activity_status == "completed" else f"Command {activity_status}",
            command_id=command.id, intent=intent, result_status=activity_status,
            severity="info" if activity_status == "completed" else "warning", source="command_api",
            correlation_id=str(command.id), idempotency_key=f"command.terminal:{command.id}")
    if result.approval_id:
        add_activity(session, user_id=command.user_id, actor_user_id=command.user_id,
            activity_type=ActivityType.APPROVAL_REQUESTED, summary="Approval requested",
            command_id=command.id, approval_id=result.approval_id, intent=intent,
            result_status="pending", source="approval", correlation_id=str(command.id),
            idempotency_key=f"approval.requested:{result.approval_id}")
    message = result.error or ("Action completed." if result.success else "Approval is required." if result.approval_required else "The action was not executed.")
    response = CommandResult(command_id=command.id, status=statuses[result.status], intent=intent,
        result=result.result, message=message, execution=_execution_payload(result))
    _cache_command_response(command, response)
    session.commit()
    return response


@router.post("/actions", response_model=CommandResult, status_code=status.HTTP_200_OK)
def execute_registered_action(request: ActionRequest, user: User = Depends(get_current_user),
    session: Session = Depends(get_session)) -> CommandResult:
    command = Command(user_id=user.id, text=f"User action request: {request.action}")
    session.add(command)
    try:
        session.flush()
        add_activity(session, user_id=user.id, actor_user_id=user.id,
            activity_type=ActivityType.COMMAND_RECEIVED, summary="Action received",
            command_id=command.id, correlation_id=str(command.id), source="actions_api",
            idempotency_key=f"command.received:{command.id}")
        ensure_user_preferences(session, user)
        autonomy = session.scalar(select(UserPreferences).where(UserPreferences.user_id == user.id))
        result = EXECUTION_ENGINE.execute(request, ActionContext(session=session, user_id=user.id,
            command_id=command.id, permissions=_user_action_permissions(session, user.id), command_text=command.text,
            autonomy_mode=autonomy.autonomy_mode if autonomy else "balanced", custom_autonomy=autonomy.custom_autonomy if autonomy else {}))
        return _commit_execution_result(session, command, request.action.upper(), result)
    except SQLAlchemyError as exc:
        session.rollback()
        logger.exception("Database failure while executing registered action", extra={"user_id": str(user.id)})
        raise HTTPException(status_code=503, detail="Orin could not save this action. Please retry shortly.") from exc


@router.post("/approvals/{approval_id}/decision", response_model=CommandResult)
def decide_approval(approval_id: uuid.UUID, decision: ApprovalDecision, user: User = Depends(get_current_user),
    session: Session = Depends(get_session)) -> CommandResult:
    approval = session.scalar(select(Approval).where(Approval.id == approval_id, Approval.requested_by_id == user.id).with_for_update())
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.status != ApprovalStatus.PENDING or not approval.action_name or approval.action_payload is None:
        raise HTTPException(status_code=409, detail="Approval request is no longer pending")
    command = session.get(Command, approval.command_id) if approval.command_id else None
    if command is None or command.user_id != user.id:
        raise HTTPException(status_code=404, detail="Approval request not found")
    expiry = approval.expires_at.replace(tzinfo=timezone.utc) if approval.expires_at and approval.expires_at.tzinfo is None else approval.expires_at
    if expiry and expiry <= datetime.now(timezone.utc):
        approval.status = ApprovalStatus.EXPIRED
        session.commit()
        raise HTTPException(status_code=409, detail="Approval request has expired")
    approval.status = ApprovalStatus.APPROVED if decision.approved else ApprovalStatus.REJECTED
    approval.decided_by_id = user.id
    approval.decision_note = decision.note
    approval.decided_at = datetime.now(timezone.utc)
    add_activity(session, user_id=user.id, actor_user_id=user.id,
        activity_type=ActivityType.APPROVAL_DECIDED,
        summary="Approval approved" if decision.approved else "Approval denied",
        command_id=command.id, approval_id=approval.id,
        result_status="approved" if decision.approved else "denied",
        source="approval", correlation_id=str(command.id),
        idempotency_key=f"approval.decision:{approval.id}")
    worker_job = session.scalar(select(WorkerJob).where(WorkerJob.approval_id == approval.id).with_for_update())
    if worker_job is not None:
        worker_job.status = WorkerJobStatus.QUEUED if decision.approved else WorkerJobStatus.CANCELLED
        if not decision.approved:
            worker_job.finished_at = datetime.now(timezone.utc)
        if decision.approved:
            add_activity(session, user_id=user.id, actor_user_id=user.id,
                activity_type=ActivityType.WORKER_JOB_QUEUED, summary="Worker job queued",
                command_id=command.id, approval_id=approval.id, worker_job_id=worker_job.id,
                result_status="queued", source="worker", correlation_id=str(command.id),
                idempotency_key=f"worker.queued:{worker_job.id}")
        else:
            add_activity(session, user_id=user.id, actor_user_id=user.id,
                activity_type=ActivityType.WORKER_JOB_FAILED, summary="Worker job denied",
                command_id=command.id, approval_id=approval.id, worker_job_id=worker_job.id,
                result_status="cancelled", severity="warning", source="worker",
                correlation_id=str(command.id), idempotency_key=f"worker.terminal:{worker_job.id}")
        session.commit()
        return CommandResult(command_id=command.id, status="approved" if decision.approved else "denied",
            intent="WORKER_ACTION", result={"job_id": str(worker_job.id), "status": worker_job.status.value},
            message="Approved worker job is queued for its registered device." if decision.approved else "Worker job rejected; no work was sent.")
    ensure_user_preferences(session, user)
    autonomy = session.scalar(select(UserPreferences).where(UserPreferences.user_id == user.id))
    result = EXECUTION_ENGINE.execute(ActionRequest(action=approval.action_name, inputs=approval.action_payload),
        ActionContext(session=session, user_id=user.id, command_id=command.id,
            permissions=_user_action_permissions(session, user.id), approval_id=approval.id, command_text=command.text,
            autonomy_mode=autonomy.autonomy_mode if autonomy else "balanced", custom_autonomy=autonomy.custom_autonomy if autonomy else {}))
    if result.success:
        approval.status = ApprovalStatus.EXECUTED
    return _commit_execution_result(session, command, approval.action_name.upper(), result)


def _approval_view(row: Approval) -> dict[str, object]:
    return {"id": row.id, "status": row.status.value, "action": row.action_name,
        "parameters": row.action_payload or {}, "risk_level": row.risk_level or "medium",
        "permission": row.permission, "reversible": row.reversible, "reason": row.decision_note,
        "created_at": row.created_at, "expires_at": row.expires_at, "decided_at": row.decided_at}


@router.get("/approvals")
def list_approvals(status_filter: str | None = Query(default=None, alias="status"), user: User = Depends(get_current_user),
                   session: Session = Depends(get_session)) -> list[dict[str, object]]:
    query = select(Approval).where(Approval.requested_by_id == user.id).order_by(Approval.created_at.desc())
    rows = session.scalars(query).all()
    now = datetime.now(timezone.utc)
    for row in rows:
        expiry = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at and row.expires_at.tzinfo is None else row.expires_at
        if row.status == ApprovalStatus.PENDING and expiry and expiry <= now:
            row.status = ApprovalStatus.EXPIRED
            command_id = row.command_id
            add_activity(session, user_id=user.id, actor_user_id=None,
                activity_type=ActivityType.APPROVAL_DECIDED, summary="Approval expired",
                command_id=command_id, approval_id=row.id, result_status="expired",
                severity="warning", source="approval",
                correlation_id=str(command_id or row.id), idempotency_key=f"approval.decision:{row.id}")
    session.commit()
    return [_approval_view(row) for row in rows if status_filter is None or row.status.value == status_filter]


@router.get("/approvals/{approval_id}")
def get_approval(approval_id: uuid.UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    row = session.scalar(select(Approval).where(Approval.id == approval_id, Approval.requested_by_id == user.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return _approval_view(row)


@router.post("/approvals/{approval_id}/cancel")
def cancel_approval(approval_id: uuid.UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    row = session.scalar(select(Approval).where(Approval.id == approval_id, Approval.requested_by_id == user.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if row.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=409, detail="Approval request is no longer pending")
    row.status = ApprovalStatus.CANCELLED
    command_id = row.command_id
    add_activity(session, user_id=user.id, actor_user_id=user.id,
        activity_type=ActivityType.APPROVAL_DECIDED, summary="Approval cancelled",
        command_id=command_id, approval_id=row.id, result_status="cancelled",
        severity="warning", source="approval", correlation_id=str(command_id or row.id),
        idempotency_key=f"approval.decision:{row.id}")
    worker_job = session.scalar(select(WorkerJob).where(WorkerJob.approval_id == row.id).with_for_update())
    if worker_job is not None and worker_job.status == WorkerJobStatus.PENDING_APPROVAL:
        worker_job.status = WorkerJobStatus.CANCELLED
        worker_job.finished_at = datetime.now(timezone.utc)
        add_activity(session, user_id=user.id, actor_user_id=user.id,
            activity_type=ActivityType.WORKER_JOB_CANCELLED, summary="Worker job cancelled",
            approval_id=row.id, worker_job_id=worker_job.id, result_status="cancelled",
            severity="warning", source="worker", correlation_id=str(command_id or row.id),
            idempotency_key=f"worker.terminal:{worker_job.id}")
    row.decided_by_id = user.id
    row.decided_at = datetime.now(timezone.utc)
    session.commit()
    return _approval_view(row)


@router.get("/users/me/preferences", response_model=PreferencesRead)
def get_user_preferences(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> dict[str, object]:
    preferences = ensure_user_preferences(session, user)
    result = preference_view(session, user, preferences)
    session.commit()
    return result


@router.put("/users/me/preferences", response_model=PreferencesRead)
def put_user_preferences(
    data: PreferencesUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    preferences = update_preferences(session, user, data)
    result = preference_view(session, user, preferences)
    session.commit()
    return result


@router.get("/capabilities", response_model=list[CapabilityRead])
def list_capabilities(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    capabilities = ensure_capability_catalog(session)
    assignments: dict[uuid.UUID, UserCapability] = {}
    ensure_user_preferences(session, user)
    assignments = {
        row.capability_id: row
        for row in session.scalars(select(UserCapability).where(UserCapability.user_id == user.id)).all()
    }
    session.commit()
    return [
        {
            "code": item.code,
            "name": item.name,
            "description": item.description,
            "granted": item.is_enabled and assignments.get(item.id) is not None and assignments[item.id].granted,
            "visible": assignments[item.id].visible if item.id in assignments else False,
            "pinned": assignments[item.id].pinned if item.id in assignments else False,
        }
        for item in capabilities
    ]


@router.get("/projects", response_model=list[ProjectRead])
def list_projects(
    user: User = Depends(get_current_user),
    status_filter: ProjectStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[Project]:
    statement = select(Project).where(Project.owner_id == user.id)
    if status_filter is not None:
        statement = statement.where(Project.status == status_filter)
    return list(session.scalars(statement.order_by(Project.updated_at.desc()).limit(limit).offset(offset)).all())


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    data: ProjectCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Project:
    project = Project(owner_id=user.id, name=data.name.strip(), description=data.description, objective=data.objective)
    session.add(project)
    session.flush()
    add_project_owner_membership(session, project)
    add_activity(session, user_id=user.id, actor_user_id=user.id, project_id=project.id, activity_type=ActivityType.PROJECT_CREATED, summary=f"Created project: {project.name}")
    session.commit()
    session.refresh(project)
    return project


@router.patch("/projects/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Project:
    project = session.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        changes["name"] = changes["name"].strip()
    for field, value in changes.items():
        setattr(project, field, value)
    add_activity(session, user_id=user.id, actor_user_id=user.id, project_id=project.id, activity_type=ActivityType.PROJECT_UPDATED, summary=f"Updated project: {project.name}")
    session.commit()
    session.refresh(project)
    return project


def ensure_project_access(session: Session, project_id: uuid.UUID, user_id: uuid.UUID) -> Project | None:
    return session.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user_id))


@router.get("/tasks", response_model=list[TaskRead])
def list_tasks(
    user: User = Depends(get_current_user),
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    project_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[Task]:
    statement = select(Task).where(Task.owner_id == user.id)
    if status_filter is not None:
        statement = statement.where(Task.status == status_filter)
    if project_id is not None:
        statement = statement.where(Task.project_id == project_id)
    return list(session.scalars(statement.order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc()).limit(limit).offset(offset)).all())


def validate_task_links(session: Session, user_id: uuid.UUID, project_id: uuid.UUID | None, assignee_id: uuid.UUID | None) -> None:
    if project_id is not None and ensure_project_access(session, project_id, user_id) is None:
        raise HTTPException(status_code=422, detail="Project is not available to this user")
    if assignee_id is not None:
        require_user(session, assignee_id)


@router.post("/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    data: TaskCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Task:
    validate_task_links(session, user.id, data.project_id, data.assignee_id)
    task = Task(owner_id=user.id, **data.model_dump())
    session.add(task)
    session.flush()
    add_activity(session, user_id=user.id, actor_user_id=user.id, project_id=task.project_id, task_id=task.id, activity_type=ActivityType.TASK_CREATED, summary=f"Created task: {task.title}")
    session.commit()
    session.refresh(task)
    return task


@router.patch("/tasks/{task_id}", response_model=TaskRead)
def update_task(
    task_id: uuid.UUID,
    data: TaskUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Task:
    task = session.scalar(select(Task).where(Task.id == task_id, Task.owner_id == user.id))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    changes = data.model_dump(exclude_unset=True)
    validate_task_links(session, user.id, changes.get("project_id", task.project_id), changes.get("assignee_id", task.assignee_id))
    if "title" in changes and changes["title"] is not None:
        changes["title"] = changes["title"].strip()
    for field, value in changes.items():
        setattr(task, field, value)
    add_activity(session, user_id=user.id, actor_user_id=user.id, project_id=task.project_id, task_id=task.id, activity_type=ActivityType.TASK_UPDATED, summary=f"Updated task: {task.title}")
    session.commit()
    session.refresh(task)
    return task


@router.get("/activity", response_model=list[ActivityRead])
def list_activity(
    user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    project_id: uuid.UUID | None = None,
    event_type: ActivityType | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    execution_id: uuid.UUID | None = None,
    command_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    session: Session = Depends(get_session),
) -> list[Activity]:
    if since is not None and until is not None and since > until:
        raise HTTPException(status_code=422, detail="since must be earlier than or equal to until")
    statement = select(Activity).where(Activity.user_id == user.id).order_by(Activity.created_at.desc(), Activity.id.desc())
    if project_id is not None:
        statement = statement.where(Activity.project_id == project_id)
    if event_type is not None:
        statement = statement.where(Activity.activity_type == event_type)
    if status_filter is not None:
        statement = statement.where(Activity.result_status == status_filter)
    if execution_id is not None:
        statement = statement.where(Activity.execution_id == execution_id)
    if command_id is not None:
        statement = statement.where(Activity.command_id == command_id)
    if since is not None:
        statement = statement.where(Activity.created_at >= since)
    if until is not None:
        statement = statement.where(Activity.created_at <= until)
    return list(session.scalars(statement.limit(limit).offset(offset)).all())


@router.get("/activity/{activity_id}", response_model=ActivityRead)
def get_activity_detail(activity_id: uuid.UUID, user: User = Depends(get_current_user),
                        session: Session = Depends(get_session)) -> Activity:
    row = session.scalar(select(Activity).where(Activity.id == activity_id, Activity.user_id == user.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return row
    if approval.expires_at and approval.expires_at <= datetime.now(timezone.utc):
        approval.status = ApprovalStatus.EXPIRED
        session.commit()
        raise HTTPException(status_code=409, detail="Approval request has expired")
