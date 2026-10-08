from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy import or_, select
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
    Project,
    ProjectStatus,
    Task,
    TaskStatus,
    TaskPriority,
    User,
    UserCapability,
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

router = APIRouter(prefix="/api/v1", tags=["core"])


@router.post("/commands", response_model=CommandResult, status_code=status.HTTP_200_OK)
def submit_command(
    data: CommandCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CommandResult:
    command = Command(user_id=user.id, text=data.text, status=CommandStatus.SUBMITTED)
    session.add(command)
    session.flush()
    try:
        if not settings.ai_provider or not settings.ai_model:
            raise AIProviderError("AI command interpretation is not configured")
        model = ModelSelector(settings.ai_model).select(AITaskType.COMMAND_INTERPRETATION)
        proposal = AIInterpreter(create_provider(settings), model).interpret(data.text)
        p = proposal.parameters
        if proposal.intent == IntentName.RESPOND:
            command.status = CommandStatus.COMPLETED
            session.commit()
            return CommandResult(
                command_id=command.id,
                status="completed",
                intent=proposal.intent.value,
                result={"response": p.response or "Hello! What would you like help with?"},
                message=p.response or "Hello! What would you like help with?",
            )
        if proposal.intent == IntentName.UNSUPPORTED:
            command.status = CommandStatus.FAILED
            session.commit()
            return CommandResult(command_id=command.id, status="unsupported", intent="UNSUPPORTED", message="This request is not supported.")

        result: dict[str, object] | list[dict[str, object]] | None
        if proposal.intent == IntentName.CREATE_TASK:
            project_id = uuid.UUID(p.project_id) if p.project_id else None
            validate_task_links(session, user.id, project_id, None)
            due_at = datetime.fromisoformat(p.due_at.replace("Z", "+00:00")) if p.due_at else None
            task = Task(owner_id=user.id, title=p.title or "", description=p.description, due_at=due_at, project_id=project_id)
            session.add(task)
            session.flush()
            command.task_id = task.id
            add_activity(session, user_id=user.id, actor_user_id=user.id, project_id=task.project_id, task_id=task.id, activity_type=ActivityType.TASK_CREATED, summary=f"Created task: {task.title}")
            result = {"id": str(task.id), "title": task.title, "status": task.status.value}
        elif proposal.intent in (IntentName.UPDATE_TASK, IntentName.COMPLETE_TASK):
            task_id = uuid.UUID(p.task_id or "")
            task = session.scalar(select(Task).where(Task.id == task_id, Task.owner_id == user.id))
            if task is None:
                raise HTTPException(status_code=404, detail="Task not found")
            changes = {"status": TaskStatus.DONE} if proposal.intent == IntentName.COMPLETE_TASK else dict(p.fields_to_update or {})
            if "project_id" in changes and changes["project_id"] is not None:
                changes["project_id"] = uuid.UUID(str(changes["project_id"]))
            try:
                validated = TaskUpdate.model_validate(changes)
            except ValidationError as exc:
                raise HTTPException(status_code=422, detail="Task update parameters are invalid") from exc
            changes = validated.model_dump(exclude_unset=True)
            validate_task_links(session, user.id, changes.get("project_id", task.project_id), task.assignee_id)
            for field, value in changes.items():
                setattr(task, field, value)
            command.task_id = task.id
            add_activity(session, user_id=user.id, actor_user_id=user.id, project_id=task.project_id, task_id=task.id, activity_type=ActivityType.TASK_UPDATED, summary=f"Updated task: {task.title}")
            result = {"id": str(task.id), "title": task.title, "status": task.status.value}
        elif proposal.intent == IntentName.CREATE_PROJECT:
            project = Project(owner_id=user.id, name=p.name or "", description=p.description)
            session.add(project)
            session.flush()
            add_project_owner_membership(session, project)
            command.project_id = project.id
            add_activity(session, user_id=user.id, actor_user_id=user.id, project_id=project.id, activity_type=ActivityType.PROJECT_CREATED, summary=f"Created project: {project.name}")
            result = {"id": str(project.id), "name": project.name, "status": project.status.value}
        elif proposal.intent == IntentName.LIST_PROJECTS:
            statement = select(Project).where(Project.owner_id == user.id)
            if p.status is not None:
                statement = statement.where(Project.status == ProjectStatus(p.status))
            rows = session.scalars(statement.order_by(Project.updated_at.desc()).limit(p.limit or 50)).all()
            result = [{"id": str(row.id), "name": row.name, "status": row.status.value} for row in rows]
        elif proposal.intent == IntentName.LIST_TASKS:
            statement = select(Task).where(Task.owner_id == user.id)
            if p.status is not None:
                statement = statement.where(Task.status == TaskStatus(p.status))
            if p.project_id is not None:
                project_id = uuid.UUID(p.project_id)
                validate_task_links(session, user.id, project_id, None)
                statement = statement.where(Task.project_id == project_id)
            rows = session.scalars(statement.order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc()).limit(p.limit or 50)).all()
            result = [{"id": str(row.id), "title": row.title, "status": row.status.value} for row in rows]
        elif proposal.intent == IntentName.GET_ACTIVITY:
            rows = session.scalars(select(Activity).where(Activity.user_id == user.id).order_by(Activity.created_at.desc()).limit(p.limit or 50)).all()
            result = [{"id": str(row.id), "activity_type": row.activity_type.value, "summary": row.summary, "created_at": row.created_at.isoformat()} for row in rows]
        else:
            raise HTTPException(status_code=422, detail="Unsupported command intent")
        command.status = CommandStatus.COMPLETED
        session.commit()
        return CommandResult(command_id=command.id, status="completed", intent=proposal.intent.value, result=result, message="Command completed.")
    except AIProviderError as exc:
        command.status = CommandStatus.FAILED
        session.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ValueError, ValidationError) as exc:
        session.rollback()
        command.status = CommandStatus.FAILED
        session.add(command)
        session.commit()
        raise HTTPException(status_code=422, detail="Command parameters are invalid") from exc
    except HTTPException:
        command.status = CommandStatus.FAILED
        session.commit()
        raise


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
    project = Project(owner_id=user.id, name=data.name.strip(), description=data.description)
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
    session: Session = Depends(get_session),
) -> list[Activity]:
    statement = select(Activity).where(Activity.user_id == user.id).order_by(Activity.created_at.desc(), Activity.id.desc())
    return list(session.scalars(statement.limit(limit).offset(offset)).all())
