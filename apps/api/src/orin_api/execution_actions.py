"""Registered Orin action definitions and their controlled database adapters."""
from __future__ import annotations

import uuid
import re
import json
from enum import Enum
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Protocol

from fastapi import HTTPException
from pydantic import Field, model_validator
from sqlalchemy import func, select

from orin_api.execution import (
    ActionContext, ActionDefinition, ActionExecutionError, ActionRegistry, ActionStatus, Reversibility,
    RiskLevel, StrictActionInput,
)
from orin_api.models import (
    Activity, ActivityType, Approval, ApprovalStatus, Command, CommandStatus, ExecutionAudit,
    DeviceStatus, EnvironmentPreference, FocusSession, Memory, Project, ProjectStatus, ProjectMember,
    ProjectRole, Task, TaskPriority, TaskStatus, User, UserCapability, WorkerDevice, Capability,
    EnergyLevel, FocusState,
)
from orin_api.schemas import TaskCreate, TaskUpdate
from orin_api.focus_domain import touch_task
from orin_api.services import add_activity, ensure_user_preferences
from orin_api.worker_service import queue_user_job


def _json_safe(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


class CreateTaskInput(StrictActionInput):
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    due_at: str | None = None
    project_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    priority: str = Field(default="normal", pattern=r"^(low|normal|high|urgent)$")
    first_step: str | None = Field(default=None, max_length=500)
    why: str | None = Field(default=None, max_length=500)
    energy_level: Literal["low", "medium", "high"] | None = None
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)
    trigger: str | None = Field(default=None, max_length=240)

    @model_validator(mode="after")
    def validate_task_role_fields(self) -> CreateTaskInput:
        if self.assignee_id is not None:
            from orin_api.models import User

            if context := getattr(self, "context", None):
                user = context.session.get(User, self.assignee_id)
                if user is None or user.owner_id != context.user_id:
                    raise ValueError("Assignee must be an owned workspace user.")
        return self


class BatchTaskItem(StrictActionInput):
    id: str | None = None
    title: str | None = None
    description: str | None = None
    due_at: str | None = None
    project_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    priority: str | None = None


class BatchTaskInput(StrictActionInput):
    tasks: list[BatchTaskItem] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_batch(self) -> BatchTaskInput:
        for index, item in enumerate(self.tasks):
            title = item.title
            if not title or not str(title).strip():
                raise ValueError(f"Task at index {index} is missing a title.")
        return self


class UpdateTaskInput(StrictActionInput):
    task_id: uuid.UUID | None = None
    task_reference: str | None = None
    fields_to_update: dict[str, Any]


class CompleteTaskInput(StrictActionInput):
    task_id: uuid.UUID | None = None
    task_reference: str | None = None


class BreakDownTaskInput(StrictActionInput):
    task_id: uuid.UUID | None = None
    task_reference: str | None = Field(default=None, min_length=1, max_length=240)
    first_step: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def require_task_reference(self) -> BreakDownTaskInput:
        if self.task_id is None and self.task_reference is None:
            raise ValueError("A task identifier or reference is required")
        return self


class EnergyTodayInput(StrictActionInput):
    energy_level: Literal["low", "medium", "high"]


class SwapTaskInput(StrictActionInput):
    task_id: uuid.UUID | None = None


class DriftActionInput(StrictActionInput):
    task_id: uuid.UUID | None = None
    task_reference: str | None = Field(default=None, min_length=1, max_length=240)
    focus_session_id: uuid.UUID | None = None
    trigger_type: Literal["app", "thought", "emotion", "person", "tired", "other"] = "other"


class ReleaseTaskInput(StrictActionInput):
    task_id: uuid.UUID | None = None
    task_reference: str | None = Field(default=None, min_length=1, max_length=240)

    @model_validator(mode="after")
    def require_task_reference(self) -> ReleaseTaskInput:
        if self.task_id is None and self.task_reference is None:
            raise ValueError("A task identifier or reference is required")
        return self


class EndFocusInput(StrictActionInput):
    focus_session_id: uuid.UUID | None = None


class DailyCloseActionInput(StrictActionInput):
    drift_triggers: list[Literal["app", "thought", "emotion", "person", "tired", "other"]] = Field(default_factory=list, max_length=6)
    tomorrow_task_reference: str | None = Field(default=None, min_length=1, max_length=240)
    reflection: str | None = Field(default=None, max_length=4000)


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
    memory_timing: str | None = Field(default=None, max_length=240)
    memory_status: Literal["not_started", "in_progress", "completed"] | None = None
    memory_acceptance_criteria: list[str] | None = Field(default=None, max_length=20)
    memory_completion_rule: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_commitment_details(self) -> SaveMemoryInput:
        if self.memory_type == "commitment" and (not self.memory_timing or not self.memory_status
                or not self.memory_acceptance_criteria or not self.memory_completion_rule):
            raise ValueError("Commitments require timing, status, acceptance criteria, and a completion rule")
        return self


class StartFocusInput(StrictActionInput):
    project_reference: str | None = Field(default=None, min_length=1, max_length=160)
    task_id: uuid.UUID | None = None
    task_reference: str | None = Field(default=None, min_length=1, max_length=240)
    objective: str | None = Field(default=None, min_length=1, max_length=500)
    duration_minutes: int = Field(default=25, ge=5, le=480)

    @model_validator(mode="after")
    def require_target(self) -> StartFocusInput:
        has_task = self.task_id is not None or self.task_reference is not None
        if bool(self.project_reference) == has_task:
            raise ValueError("Choose exactly one task or project to focus on")
        return self


class SetToolVisibilityInput(StrictActionInput):
    tool: Literal["home", "projects", "tasks", "activity", "memories", "focus"]
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
    title = data.memory_title.strip()
    # A retried explicit save should update the same owned memory, not create a
    # second copy. Matching is deliberately narrow: owner, type, scope and title.
    memory = context.session.scalar(select(Memory).where(
        Memory.user_id == context.user_id, Memory.project_id == (project.id if project else None),
        Memory.memory_type == data.memory_type, Memory.title.ilike(title), Memory.archived.is_(False),
    ).order_by(Memory.updated_at.desc()).limit(1))
    if memory is None:
        memory = Memory(user_id=context.user_id, project_id=project.id if project else None,
            memory_type=data.memory_type, title=title, content=data.memory_content.strip(),
            source="explicit user command", confidence=0.9,
            metadata_json={"timing": data.memory_timing, "status": data.memory_status,
                "acceptance_criteria": data.memory_acceptance_criteria,
                "completion_rule": data.memory_completion_rule})
        context.session.add(memory)
    else:
        memory.content = data.memory_content.strip()
        memory.source = "explicit user command"
        memory.metadata_json = {"timing": data.memory_timing, "status": data.memory_status,
            "acceptance_criteria": data.memory_acceptance_criteria,
            "completion_rule": data.memory_completion_rule}
    context.session.flush()
    add_activity(context.session, user_id=context.user_id, actor_user_id=context.user_id,
        project_id=memory.project_id, activity_type=ActivityType.MEMORY_CHANGED,
        summary=f"Saved memory: {memory.title}", command_id=context.command_id)
    return {"id": str(memory.id), "title": memory.title, "type": memory.memory_type,
        "content": memory.content, "metadata": memory.metadata_json, "entity_type": "memory"}


def _start_focus(context: ActionContext, raw: StartFocusInput) -> dict[str, Any]:
    data = StartFocusInput.model_validate(raw)
    user = context.session.get(User, context.user_id)
    if user is None:
        raise ActionExecutionError("User not found.", status=ActionStatus.DENIED)
    try:
        from orin_api import focus_router, workspace_router
        if data.task_id is not None or data.task_reference is not None:
            task = _resolve_task(context, data.task_id, data.task_reference)
            current = focus_router.get_now(user, context.session).get("task")
            if not isinstance(current, dict) or str(current.get("id")) != str(task.id):
                raise ActionExecutionError("Choose that task in Today before starting its focus session.")
            duration = data.duration_minutes if "duration_minutes" in data.model_fields_set else min(max(task.estimated_minutes or 25, 5), 480)
            focus = workspace_router.start_focus(workspace_router.FocusCreate(
                project_id=task.project_id, task_id=task.id,
                objective=(data.objective or task.title).strip(), duration_minutes=duration), user, context.session)
            from orin_api.focus_domain import set_focus_state
            set_focus_state(task, FocusState.ACTIVE)
            context.session.commit()
            return _json_safe({**focus, "entity_type": "focus_session"})
        project = _owned_project_by_name(context, data.project_reference or "")
        if not data.objective:
            raise ActionExecutionError("A focus objective is required for a project session.", status=ActionStatus.INVALID)
        focus = workspace_router.start_focus(workspace_router.FocusCreate(
            project_id=project.id, objective=data.objective.strip(), duration_minutes=data.duration_minutes), user, context.session)
        return _json_safe({**focus, "entity_type": "focus_session"})
    except HTTPException as exc:
        _raise_route_error(exc)


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
    user = context.session.get(User, context.user_id)
    if user is None:
        raise ActionExecutionError("User not found.", status=ActionStatus.DENIED)
    try:
        data = TaskCreate(title=raw.title, description=raw.description,
            due_at=datetime.fromisoformat(raw.due_at.replace("Z", "+00:00")) if raw.due_at else None,
            project_id=raw.project_id, assignee_id=raw.assignee_id,
            priority=TaskPriority(raw.priority), first_step=raw.first_step, why=raw.why,
            energy_level=EnergyLevel(raw.energy_level) if raw.energy_level else None,
            estimated_minutes=raw.estimated_minutes, trigger=raw.trigger)
        from orin_api.domain_router import create_task as create_task_route
        task = create_task_route(data, user, context.session)
    except HTTPException as exc:
        _raise_route_error(exc)
    except (TypeError, ValueError) as exc:
        raise ActionExecutionError("Task fields are invalid.", status=ActionStatus.INVALID) from exc
    return {
        "id": str(task.id),
        "entity_type": "task",
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "priority": task.priority.value,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "project_id": str(task.project_id) if task.project_id else None,
        "assignee_id": str(task.assignee_id) if task.assignee_id else None,
        "owner_id": str(task.owner_id),
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def _create_tasks_batch(context: ActionContext, raw: BatchTaskInput) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for index, item in enumerate(raw.tasks):
        try:
            unique_id = item.id or str(uuid.uuid4())
            title = (item.title or "").strip()
            if not title:
                failed.append({"index": index, "id": unique_id, "title": "", "error": "Task title is required."})
                continue
            project_id = item.project_id
            if project_id is not None:
                project = context.session.scalar(select(Project).where(Project.id == project_id, Project.owner_id == context.user_id))
                if project is None:
                    raise ActionExecutionError("Project not found in your workspace.", status=ActionStatus.DENIED)
            assignee_id = item.assignee_id
            if assignee_id is not None:
                assignee = context.session.scalar(select(User).where(User.id == assignee_id, User.owner_id == context.user_id))
                if assignee is None:
                    raise ActionExecutionError("Assignee not found in your workspace.", status=ActionStatus.DENIED)
            due_at = None
            if item.due_at:
                try:
                    due_at = datetime.fromisoformat(item.due_at.replace("Z", "+00:00"))
                except ValueError:
                    raise ActionExecutionError("Task due date is not a valid ISO-8601 timestamp.", status=ActionStatus.DENIED)
            priority = TaskPriority(item.priority) if item.priority else TaskPriority.NORMAL
            task = Task(
                owner_id=context.user_id,
                title=title,
                description=item.description,
                due_at=due_at,
                project_id=project_id,
                assignee_id=assignee_id,
                priority=priority,
            )
            touch_task(task)
            context.session.add(task)
            context.session.flush()
            created.append({"index": index, "id": str(task.id), "title": task.title, "status": task.status.value, "entity_type": "task"})
        except ActionExecutionError as exc:
            failed.append({"index": index, "id": str(uuid.uuid4()), "title": (item.title or "").strip(), "error": str(exc)})
        except ValueError as exc:
            failed.append({"index": index, "id": str(uuid.uuid4()), "title": (item.title or "").strip(), "error": "Task priority is not a valid enum value."})
    if failed:
        result = {"created": created, "failed": failed, "success": True}
    else:
        result = {"created": created, "failed": [], "success": True}
    context.session.flush()
    add_activity(context.session, user_id=context.user_id, actor_user_id=context.user_id,
        activity_type=ActivityType.TASKS_CREATED_BATCH, summary=f"Batch created {len(created)} tasks; {len(failed)} failed.",
        command_id=context.command_id, intent="CREATE_TASKS_BATCH")
    return result


def _update_task(context: ActionContext, raw: UpdateTaskInput) -> dict[str, Any]:
    task = _resolve_task(context, raw.task_id, raw.task_reference)
    try:
        data = TaskUpdate.model_validate(raw.fields_to_update)
        user = context.session.get(User, context.user_id)
        from orin_api.domain_router import update_task as update_task_route
        task = update_task_route(task.id, data, user, context.session,
            command_id=context.command_id, intent="UPDATE_TASK")
    except HTTPException as exc:
        _raise_route_error(exc)
    except Exception as exc:
        raise ActionExecutionError("Task update parameters are invalid.", status=ActionStatus.INVALID) from exc
    return {"id": str(task.id), "title": task.title, "status": task.status.value, "entity_type": "task"}


def _complete_task(context: ActionContext, raw: CompleteTaskInput) -> dict[str, Any]:
    task = _resolve_task(context, raw.task_id, raw.task_reference)
    user = context.session.get(User, context.user_id)
    try:
        from orin_api.domain_router import update_task as update_task_route
        task = update_task_route(task.id, TaskUpdate(status=TaskStatus.DONE), user, context.session,
            command_id=context.command_id, intent="COMPLETE_TASK")
    except HTTPException as exc:
        _raise_route_error(exc)
    return {"id": str(task.id), "title": task.title, "status": task.status.value, "entity_type": "task"}


def _break_down_task(context: ActionContext, raw: BreakDownTaskInput) -> dict[str, Any]:
    task = _resolve_task(context, raw.task_id, raw.task_reference)
    return _update_task(context, UpdateTaskInput(task_id=task.id,
        fields_to_update={"first_step": raw.first_step.strip()}))


def _set_energy_today(context: ActionContext, raw: EnergyTodayInput) -> dict[str, Any]:
    user = context.session.get(User, context.user_id)
    try:
        from orin_api.focus_router import EnergyUpdate, set_energy
        result = set_energy(EnergyUpdate(energy_level=EnergyLevel(raw.energy_level)), user, context.session)
    except HTTPException as exc:
        _raise_route_error(exc)
    return {**result, "entity_type": "focus_settings"}


def _propose_todays_three(context: ActionContext, _raw: StrictActionInput) -> dict[str, Any]:
    user = context.session.get(User, context.user_id)
    try:
        from orin_api.focus_router import propose_today
        result = propose_today(user, context.session)
    except HTTPException as exc:
        _raise_route_error(exc)
    return _json_safe({**result, "entity_type": "daily_plan"})


def _swap_task(context: ActionContext, raw: SwapTaskInput) -> dict[str, Any]:
    user = context.session.get(User, context.user_id)
    try:
        from orin_api.focus_router import SwapInput, swap_today
        result = swap_today(SwapInput(task_id=raw.task_id), user, context.session)
    except HTTPException as exc:
        _raise_route_error(exc)
    if not result.get("swapped"):
        raise ActionExecutionError(str(result.get("message") or "No suitable replacement is available."))
    task = result.get("task")
    if not isinstance(task, dict):
        raise ActionExecutionError("The replacement task could not be verified.")
    return _json_safe({**task, "entity_type": "task"})


def _log_drift(context: ActionContext, raw: DriftActionInput) -> dict[str, Any]:
    user = context.session.get(User, context.user_id)
    task_id = raw.task_id
    if raw.task_reference:
        task_id = _resolve_task(context, task_id, raw.task_reference).id
    try:
        from orin_api.focus_router import DriftCreate, create_drift_event
        result = create_drift_event(DriftCreate(task_id=task_id,
            focus_session_id=raw.focus_session_id, trigger_type=raw.trigger_type), user, context.session)
    except HTTPException as exc:
        _raise_route_error(exc)
    return _json_safe({**result, "entity_type": "drift_event"})


def _release_task(context: ActionContext, raw: ReleaseTaskInput) -> dict[str, Any]:
    task = _resolve_task(context, raw.task_id, raw.task_reference)
    user = context.session.get(User, context.user_id)
    try:
        from orin_api.focus_router import ReviewInput, review_task
        result = review_task(task.id, ReviewInput(outcome="release"), user, context.session)
    except HTTPException as exc:
        _raise_route_error(exc)
    return _json_safe({**result["task"], "entity_type": "task"})


def _end_focus_session(context: ActionContext, raw: EndFocusInput) -> dict[str, Any]:
    statement = select(FocusSession).where(FocusSession.user_id == context.user_id,
        FocusSession.status.in_(["active", "paused"]))
    if raw.focus_session_id is not None:
        statement = statement.where(FocusSession.id == raw.focus_session_id)
    focus = context.session.scalar(statement.order_by(FocusSession.started_at.desc()).with_for_update())
    if focus is None:
        raise ActionExecutionError("There is no active focus session to end.")
    user = context.session.get(User, context.user_id)
    try:
        from orin_api.workspace_router import FocusUpdate, update_focus
        result = update_focus(focus.id, FocusUpdate(action="complete"), user, context.session)
    except HTTPException as exc:
        _raise_route_error(exc)
    return _json_safe({**result, "entity_type": "focus_session"})


def _run_daily_close(context: ActionContext, raw: DailyCloseActionInput) -> dict[str, Any]:
    user = context.session.get(User, context.user_id)
    tomorrow_id = _resolve_task(context, None, raw.tomorrow_task_reference).id if raw.tomorrow_task_reference else None
    try:
        from orin_api.focus_router import DailyCloseCreate, get_close_today, save_daily_close
        current = get_close_today(user, context.session)
        result = save_daily_close(DailyCloseCreate(done_list=current["done_list"],
            tomorrow_task_id=tomorrow_id, reflection=raw.reflection,
            drift_triggers=raw.drift_triggers), user, context.session)
    except HTTPException as exc:
        _raise_route_error(exc)
    return _json_safe({**result, "entity_type": "daily_close"})


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
        ActionDefinition("break_down_task", BreakDownTaskInput, "task.update", RiskLevel.LOW, _break_down_task, Reversibility.REVERSIBLE),
        ActionDefinition("set_energy_today", EnergyTodayInput, "task.read", RiskLevel.LOW, _set_energy_today, Reversibility.REVERSIBLE),
        ActionDefinition("propose_todays_three", StrictActionInput, "task.read", RiskLevel.LOW, _propose_todays_three, Reversibility.REVERSIBLE),
        ActionDefinition("swap_task", SwapTaskInput, "task.update", RiskLevel.LOW, _swap_task, Reversibility.REVERSIBLE),
        ActionDefinition("log_drift", DriftActionInput, "task.read", RiskLevel.LOW, _log_drift, Reversibility.REVERSIBLE),
        ActionDefinition("release_task", ReleaseTaskInput, "task.update", RiskLevel.MEDIUM, _release_task, Reversibility.REVERSIBLE, requires_approval=True),
        ActionDefinition("end_focus_session", EndFocusInput, "task.read", RiskLevel.LOW, _end_focus_session, Reversibility.REVERSIBLE),
        ActionDefinition("run_daily_close", DailyCloseActionInput, "task.read", RiskLevel.LOW, _run_daily_close, Reversibility.REVERSIBLE),
        ActionDefinition("create_tasks_batch", BatchTaskInput, "task.create", RiskLevel.LOW, _create_tasks_batch, Reversibility.REVERSIBLE),
        ActionDefinition("update_task", UpdateTaskInput, "task.update", RiskLevel.LOW, _update_task, Reversibility.REVERSIBLE),
        ActionDefinition("complete_task", CompleteTaskInput, "task.complete", RiskLevel.LOW, _complete_task, Reversibility.REVERSIBLE),
        ActionDefinition("create_project", CreateProjectInput, "project.create", RiskLevel.LOW, _create_project, Reversibility.REVERSIBLE),
        ActionDefinition("list_projects", ListProjectsInput, "project.read", RiskLevel.LOW, _list_projects, Reversibility.REVERSIBLE),
        ActionDefinition("list_tasks", ListTasksInput, "task.read", RiskLevel.LOW, _list_tasks, Reversibility.REVERSIBLE),
        ActionDefinition("get_activity", GetActivityInput, "activity.read", RiskLevel.LOW, _get_activity, Reversibility.REVERSIBLE),
        ActionDefinition("request_worker_action", WorkerActionInput, "worker.execute", RiskLevel.LOW, _request_worker_action, Reversibility.PARTIAL),
        ActionDefinition("save_memory", SaveMemoryInput, "memory.write", RiskLevel.LOW, _save_memory, Reversibility.REVERSIBLE),
        ActionDefinition("start_focus_session", StartFocusInput, "focus.start", RiskLevel.LOW, _start_focus, Reversibility.REVERSIBLE),
        ActionDefinition("set_tool_visibility", SetToolVisibilityInput, "settings.personalize", RiskLevel.LOW, _set_tool_visibility, Reversibility.REVERSIBLE),
        ActionDefinition("send_notification", SendNotificationInput, "notification.send", RiskLevel.MEDIUM, send_notification, Reversibility.IRREVERSIBLE, requires_approval=notification_requires_approval),
        ActionDefinition("request_approval", RequestApprovalInput, "approval.request", RiskLevel.LOW, request_approval, Reversibility.REVERSIBLE),
    ]
    registry = ActionRegistry(definitions)
    return registry
