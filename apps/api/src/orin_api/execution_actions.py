"""Registered Orin action definitions and their controlled database adapters."""
from __future__ import annotations

import uuid
import re
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Protocol

from pydantic import Field, model_validator
from sqlalchemy import func, select

from orin_api.execution import (
    ActionContext, ActionDefinition, ActionExecutionError, ActionRegistry, ActionStatus, Reversibility,
    RiskLevel, StrictActionInput,
)
from orin_api.models import (
    Activity, ActivityType, Approval, ApprovalStatus, Command, CommandStatus, ExecutionAudit,
    DeviceStatus, EnvironmentPreference, FocusSession, Memory, Project, ProjectStatus, ProjectMember,
    ProjectRole, Task, TaskStatus, User, UserCapability, WorkerDevice, Capability,
)
from orin_api.schemas import TaskUpdate
from orin_api.services import add_activity, ensure_user_preferences
from orin_api.worker_service import queue_user_job


class CreateTaskInput(StrictActionInput):
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    due_at: str | None = None
    project_id: uuid.UUID | None = None


class UpdateTaskInput(StrictActionInput):
    task_id: uuid.UUID | None = None
    task_reference: str | None = None
    fields_to_update: dict[str, Any]


class CompleteTaskInput(StrictActionInput):
    task_id: uuid.UUID | None = None
    task_reference: str | None = None


class CreateProjectInput(StrictActionInput):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None


class ListProjectsInput(StrictActionInput):
    status: str | None = None
    limit: int = Field(default=50, ge=1, le=100)


class ListTasksInput(StrictActionInput):
    status: str | None = None
    project_id: uuid.UUID | None = None
    limit: int = Field(default=50, ge=1, le=100)


class GetActivityInput(StrictActionInput):
    limit: int = Field(default=50, ge=1, le=100)


class WorkerActionInput(StrictActionInput):
    worker_action: Literal["get_system_info", "list_directory", "read_file", "write_file", "run_allowed_command"]
    worker_parameters: dict[str, Any]

    @model_validator(mode="after")
    def validate_action_parameters(self) -> WorkerActionInput:
        try:
            from orin_api.worker_service import validate_worker_action
            validate_worker_action(self.worker_action, self.worker_parameters)
        except Exception as exc:
            raise ValueError("Worker action parameters are invalid") from exc
        return self


class SaveMemoryInput(StrictActionInput):
    memory_type: Literal["preference", "decision", "fact", "commitment", "workflow", "project_context"]
    memory_title: str = Field(min_length=1, max_length=180)
    memory_content: str = Field(min_length=1, max_length=5000)
    project_reference: str | None = Field(default=None, max_length=160)


class StartFocusInput(StrictActionInput):
    project_reference: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=1, max_length=500)
    duration_minutes: int = Field(ge=5, le=480)


class SetToolVisibilityInput(StrictActionInput):
    tool: Literal["home", "projects", "tasks", "activity"]
    visibility: Literal["visible", "hidden", "minimized", "prioritized"]


_MEMORY_SECRET = re.compile(r"(?i)(?:api[_-]?key|password|secret|token|authorization)\s*[:=]\s*\S+")


def _owned_project_by_name(context: ActionContext, reference: str) -> Project:
    rows = context.session.scalars(select(Project).where(Project.owner_id == context.user_id)).all()
    matches = [row for row in rows if row.name.casefold() == reference.strip().casefold()]
    if len(matches) != 1:
        raise ActionExecutionError("Project not found by that exact name in your workspace.", status=ActionStatus.DENIED)
    return matches[0]


def _save_memory(context: ActionContext, raw: SaveMemoryInput) -> dict[str, Any]:
    data = SaveMemoryInput.model_validate(raw)
    if _MEMORY_SECRET.search(data.memory_content):
        raise ActionExecutionError("This memory looks like it contains a secret. Orin will not store it.", status=ActionStatus.DENIED)
    project = _owned_project_by_name(context, data.project_reference) if data.project_reference else None
    memory = Memory(user_id=context.user_id, project_id=project.id if project else None,
        memory_type=data.memory_type, title=data.memory_title.strip(), content=data.memory_content.strip(),
        source="explicit user command", confidence=0.9)
    context.session.add(memory)
    context.session.flush()
    add_activity(context.session, user_id=context.user_id, actor_user_id=context.user_id,
        project_id=memory.project_id, activity_type=ActivityType.MEMORY_CHANGED,
        summary=f"Saved memory: {memory.title}", command_id=context.command_id)
    return {"id": str(memory.id), "title": memory.title, "type": memory.memory_type, "entity_type": "memory"}


def _start_focus(context: ActionContext, raw: StartFocusInput) -> dict[str, Any]:
    data = StartFocusInput.model_validate(raw)
    project = _owned_project_by_name(context, data.project_reference)
    now = datetime.now(timezone.utc)
    active = context.session.scalar(select(FocusSession).where(FocusSession.user_id == context.user_id,
        FocusSession.status == "active").with_for_update())
    if active:
        started = active.started_at.replace(tzinfo=timezone.utc) if active.started_at.tzinfo is None else active.started_at
        active.status = "expired" if started + timedelta(minutes=active.duration_minutes) <= now else "completed"
        active.ended_at = now
    focus = FocusSession(user_id=context.user_id, project_id=project.id, objective=data.objective.strip(),
        duration_minutes=data.duration_minutes, started_at=now,
        context_snapshot={"project_name": project.name, "project_objective": project.objective})
    context.session.add(focus)
    context.session.flush()
    add_activity(context.session, user_id=context.user_id, actor_user_id=context.user_id,
        project_id=project.id, activity_type=ActivityType.FOCUS_UPDATED,
        summary=f"Started focus: {focus.objective}", command_id=context.command_id)
    return {"id": str(focus.id), "project_id": str(project.id), "objective": focus.objective,
        "duration_minutes": focus.duration_minutes, "status": focus.status, "entity_type": "focus_session"}


def _set_tool_visibility(context: ActionContext, raw: SetToolVisibilityInput) -> dict[str, Any]:
    data = SetToolVisibilityInput.model_validate(raw)
    user = context.session.get(User, context.user_id)
    if user is None:
        raise ActionExecutionError("User not found.", status=ActionStatus.DENIED)
    ensure_user_preferences(context.session, user)
    assignment = context.session.scalar(select(UserCapability).join(Capability, Capability.id == UserCapability.capability_id)
        .where(UserCapability.user_id == context.user_id, Capability.code == data.tool))
    if assignment is None or not assignment.granted:
        raise ActionExecutionError("That tool is not available in your workspace.", status=ActionStatus.DENIED)
    assignment.visible = data.visibility != "hidden"
    assignment.pinned = data.visibility == "prioritized"
    preference = context.session.scalar(select(EnvironmentPreference).where(EnvironmentPreference.user_id == context.user_id,
        EnvironmentPreference.surface == "navigation", EnvironmentPreference.item == data.tool))
    if preference is None:
        preference = EnvironmentPreference(user_id=context.user_id, surface="navigation", item=data.tool)
        context.session.add(preference)
    preference.visibility = data.visibility
    preference.priority = 10 if data.visibility == "prioritized" else 0
    preference.source = "explicit"
    return {"tool": data.tool, "visibility": data.visibility}


class SendNotificationInput(StrictActionInput):
    recipient: str = Field(min_length=1, max_length=320)
    message: str = Field(min_length=1, max_length=4000)


class RequestApprovalInput(StrictActionInput):
    action: str = Field(min_length=1, max_length=80)
    inputs: dict[str, Any]
    reason: str = Field(min_length=1, max_length=1000)


class NotificationProvider(Protocol):
    def send(self, *, recipient: str, message: str) -> dict[str, Any]: ...


class UnconfiguredNotificationProvider:
    def send(self, *, recipient: str, message: str) -> dict[str, Any]:
        raise ActionExecutionError("Notification delivery is not configured.")


def _resolve_task(context: ActionContext, task_id: uuid.UUID | None, reference: str | None) -> Task:
    if task_id is not None:
        task = context.session.scalar(select(Task).where(Task.id == task_id, Task.owner_id == context.user_id))
    elif reference:
        def normalize(value: str) -> str:
            value = re.sub(r"[^\w\s-]", " ", value.casefold())
            value = re.sub(r"\s+", " ", value).strip()
            value = re.sub(r"^(?:the|my|a)\s+", "", value)
            return re.sub(r"\s+task$", "", value).strip()

        owned = context.session.scalars(select(Task).where(Task.owner_id == context.user_id)).all()
        normalized_reference = normalize(reference)
        mentioned = normalize(context.command_text)
        matches = [row for row in owned if normalize(row.title) in mentioned]
        if len(matches) != 1:
            matches = [row for row in owned if normalize(row.title) == normalized_reference]
        if not matches and normalized_reference:
            reference_words = set(normalized_reference.split())
            matches = [row for row in owned if set(normalize(row.title).split()).issubset(reference_words)]
        if len(matches) > 1:
            raise ActionExecutionError("More than one task matches that name. Please be more specific.")
        task = matches[0] if matches else None
    else:
        raise ActionExecutionError("A task identifier or exact task name is required.")
    if task is None:
        raise ActionExecutionError("Task not found in your workspace.", status=ActionStatus.DENIED)
    return task


def _create_task(context: ActionContext, raw: CreateTaskInput) -> dict[str, Any]:
    project_id = raw.project_id
    if project_id and context.session.scalar(select(Project.id).where(Project.id == project_id, Project.owner_id == context.user_id)) is None:
        raise ActionExecutionError("Project not found in your workspace.")
    due_at = datetime.fromisoformat(raw.due_at.replace("Z", "+00:00")) if raw.due_at else None
    task = Task(owner_id=context.user_id, title=raw.title.strip(), description=raw.description, due_at=due_at, project_id=project_id)
    context.session.add(task)
    context.session.flush()
    add_activity(context.session, user_id=context.user_id, actor_user_id=context.user_id, project_id=task.project_id, task_id=task.id, activity_type=ActivityType.TASK_CREATED, summary=f"Created task: {task.title}", command_id=context.command_id, intent="CREATE_TASK")
    return {"id": str(task.id), "title": task.title, "status": task.status.value, "entity_type": "task"}


def _update_task(context: ActionContext, raw: UpdateTaskInput) -> dict[str, Any]:
    task = _resolve_task(context, raw.task_id, raw.task_reference)
    try:
        changes = TaskUpdate.model_validate(raw.fields_to_update).model_dump(exclude_unset=True)
    except Exception as exc:
        raise ActionExecutionError("Task update parameters are invalid.") from exc
    project_id = changes.get("project_id", task.project_id)
    if project_id is not None and context.session.scalar(select(Project.id).where(Project.id == project_id, Project.owner_id == context.user_id)) is None:
        raise ActionExecutionError("Project not found in your workspace.")
    for field, value in changes.items():
        setattr(task, field, value)
    context.session.flush()
    add_activity(context.session, user_id=context.user_id, actor_user_id=context.user_id, project_id=task.project_id, task_id=task.id, activity_type=ActivityType.TASK_UPDATED, summary=f"Updated task: {task.title}", command_id=context.command_id, intent="UPDATE_TASK")
    return {"id": str(task.id), "title": task.title, "status": task.status.value, "entity_type": "task"}


def _complete_task(context: ActionContext, raw: CompleteTaskInput) -> dict[str, Any]:
    task = _resolve_task(context, raw.task_id, raw.task_reference)
    task.status = TaskStatus.DONE
    context.session.flush()
    add_activity(context.session, user_id=context.user_id, actor_user_id=context.user_id, project_id=task.project_id, task_id=task.id, activity_type=ActivityType.TASK_UPDATED, summary=f"Completed task: {task.title}", command_id=context.command_id, intent="COMPLETE_TASK")
    return {"id": str(task.id), "title": task.title, "status": task.status.value, "entity_type": "task"}


def _create_project(context: ActionContext, raw: CreateProjectInput) -> dict[str, Any]:
    project = Project(owner_id=context.user_id, name=raw.name.strip(), description=raw.description)
    context.session.add(project)
    context.session.flush()
    context.session.add(ProjectMember(project_id=project.id, user_id=context.user_id, role=ProjectRole.OWNER))
    add_activity(context.session, user_id=context.user_id, actor_user_id=context.user_id, project_id=project.id, activity_type=ActivityType.PROJECT_CREATED, summary=f"Created project: {project.name}", command_id=context.command_id, intent="CREATE_PROJECT")
    return {"id": str(project.id), "name": project.name, "status": project.status.value, "entity_type": "project"}


def _list_projects(context: ActionContext, raw: ListProjectsInput) -> list[dict[str, Any]]:
    statement = select(Project).where(Project.owner_id == context.user_id)
    if raw.status:
        try:
            statement = statement.where(Project.status == ProjectStatus(raw.status))
        except ValueError as exc:
            raise ActionExecutionError("Project status filter is invalid.") from exc
    rows = context.session.scalars(statement.order_by(Project.updated_at.desc()).limit(raw.limit)).all()
    return [{"id": str(row.id), "name": row.name, "status": row.status.value} for row in rows]


def _list_tasks(context: ActionContext, raw: ListTasksInput) -> list[dict[str, Any]]:
    statement = select(Task).where(Task.owner_id == context.user_id)
    if raw.status:
        try:
            statement = statement.where(Task.status == TaskStatus(raw.status))
        except ValueError as exc:
            raise ActionExecutionError("Task status filter is invalid.") from exc
    if raw.project_id:
        if context.session.scalar(select(Project.id).where(Project.id == raw.project_id, Project.owner_id == context.user_id)) is None:
            raise ActionExecutionError("Project not found in your workspace.")
        statement = statement.where(Task.project_id == raw.project_id)
    rows = context.session.scalars(statement.order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc()).limit(raw.limit)).all()
    return [{"id": str(row.id), "title": row.title, "status": row.status.value} for row in rows]


def _get_activity(context: ActionContext, raw: GetActivityInput) -> list[dict[str, Any]]:
    rows = context.session.scalars(select(Activity).where(Activity.user_id == context.user_id).order_by(Activity.created_at.desc()).limit(raw.limit)).all()
    return [{"id": str(row.id), "activity_type": row.activity_type.value, "summary": row.summary, "created_at": row.created_at.isoformat()} for row in rows]


def _request_worker_action(context: ActionContext, raw: WorkerActionInput) -> dict[str, Any]:
    data = WorkerActionInput.model_validate(raw)
    devices = context.session.scalars(select(WorkerDevice).where(
        WorkerDevice.owner_id == context.user_id, WorkerDevice.status == DeviceStatus.ACTIVE
    ).order_by(WorkerDevice.last_seen_at.desc()).limit(2)).all()
    now = datetime.now(timezone.utc)
    devices = [device for device in devices if device.last_seen_at and
               (device.last_seen_at.replace(tzinfo=timezone.utc) if device.last_seen_at.tzinfo is None else device.last_seen_at) > now - timedelta(minutes=2)]
    if len(devices) != 1:
        raise ActionExecutionError("Connect exactly one worker device before asking Orin to run a project action.")
    user = context.session.get(User, context.user_id)
    command = context.session.get(Command, context.command_id)
    if user is None or command is None:
        raise ActionExecutionError("Worker action context is unavailable.")
    job, approval = queue_user_job(context.session, user=user, device=devices[0], command=command,
        action=data.worker_action, parameters=data.worker_parameters)
    context.session.add(ExecutionAudit(user_id=context.user_id, command_id=context.command_id,
        action_name=approval.action_name or "worker_action", risk_level=approval.risk_level or "high",
        permission=approval.permission or "worker.execute", approval_required=True,
        execution_status="pending_approval", result_status="pending_approval",
        entity_type="worker_job", entity_id=str(job.id), approval_id=approval.id))
    return {"id": str(job.id), "job_id": str(job.id), "approval_id": str(approval.id),
            "status": "pending_approval", "action": job.action, "entity_type": "worker_job"}


def build_action_registry(
    notification_provider: NotificationProvider | None = None,
    *,
    notification_requires_approval: bool = True,
) -> ActionRegistry:
    provider = notification_provider or UnconfiguredNotificationProvider()

    def send_notification(_context: ActionContext, raw: BaseModel) -> dict[str, Any]:
        data = SendNotificationInput.model_validate(raw)
        return provider.send(recipient=data.recipient, message=data.message)

    def request_approval(context: ActionContext, raw: BaseModel) -> dict[str, Any]:
        data = RequestApprovalInput.model_validate(raw)
        target = registry.get(data.action)
        if target is None or not target.requires_approval:
            raise ActionExecutionError("That action does not have an approval workflow.")
        try:
            validated = target.input_schema.model_validate_json(json.dumps(data.inputs, default=str))
        except Exception as exc:
            raise ActionExecutionError("Approval request inputs are invalid.") from exc
        approval = Approval(
            command_id=context.command_id,
            requested_by_id=context.user_id,
            status=ApprovalStatus.PENDING,
            decision_note=data.reason,
            action_name=target.name,
            action_payload=validated.model_dump(mode="json"),
            risk_level=target.risk_level.value,
            permission=target.permission,
            reversible=target.reversibility != Reversibility.IRREVERSIBLE,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        context.session.add(approval)
        command = context.session.get(Command, context.command_id)
        if command:
            command.status = CommandStatus.AWAITING_APPROVAL
        context.session.flush()
        return {"id": str(approval.id), "approval_id": str(approval.id), "status": "pending_approval", "action": target.name, "entity_type": "approval"}

    definitions = [
        ActionDefinition("create_task", CreateTaskInput, "task.create", RiskLevel.LOW, _create_task, Reversibility.REVERSIBLE),
        ActionDefinition("update_task", UpdateTaskInput, "task.update", RiskLevel.LOW, _update_task, Reversibility.REVERSIBLE),
        ActionDefinition("complete_task", CompleteTaskInput, "task.complete", RiskLevel.LOW, _complete_task, Reversibility.REVERSIBLE),
        ActionDefinition("create_project", CreateProjectInput, "project.create", RiskLevel.LOW, _create_project, Reversibility.REVERSIBLE),
        ActionDefinition("list_projects", ListProjectsInput, "project.read", RiskLevel.LOW, _list_projects, Reversibility.REVERSIBLE),
        ActionDefinition("list_tasks", ListTasksInput, "task.read", RiskLevel.LOW, _list_tasks, Reversibility.REVERSIBLE),
        ActionDefinition("get_activity", GetActivityInput, "activity.read", RiskLevel.LOW, _get_activity, Reversibility.REVERSIBLE),
        ActionDefinition("request_worker_action", WorkerActionInput, "worker.execute", RiskLevel.LOW, _request_worker_action, Reversibility.PARTIAL),
        ActionDefinition("save_memory", SaveMemoryInput, "memory.write", RiskLevel.LOW, _save_memory, Reversibility.REVERSIBLE),
        ActionDefinition("start_focus_session", StartFocusInput, "project.read", RiskLevel.LOW, _start_focus, Reversibility.REVERSIBLE),
        ActionDefinition("set_tool_visibility", SetToolVisibilityInput, "settings.personalize", RiskLevel.LOW, _set_tool_visibility, Reversibility.REVERSIBLE),
        ActionDefinition("send_notification", SendNotificationInput, "notification.send", RiskLevel.MEDIUM, send_notification, Reversibility.IRREVERSIBLE, requires_approval=notification_requires_approval),
        ActionDefinition("request_approval", RequestApprovalInput, "approval.request", RiskLevel.LOW, request_approval, Reversibility.REVERSIBLE),
    ]
    registry = ActionRegistry(definitions)
    return registry
