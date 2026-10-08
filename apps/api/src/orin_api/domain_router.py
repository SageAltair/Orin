from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from orin_api.auth import get_current_user
from orin_api.database import get_session
from orin_api.models import (
    Activity,
    ActivityType,
    Capability,
    Project,
    ProjectStatus,
    Task,
    TaskStatus,
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
