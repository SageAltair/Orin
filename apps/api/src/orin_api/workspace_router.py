"""Project context, structured memory, explicit environment preferences and focus sessions."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from orin_api.auth import get_current_user
from orin_api.database import get_session
from orin_api.domain_router import ensure_project_access
from orin_api.models import Activity, ActivityType, Capability, EnvironmentPreference, FocusSession, Memory, Project, Task, TaskStatus, User, UserCapability
from orin_api.services import add_activity
from orin_api.services import ensure_user_preferences

router = APIRouter(prefix="/api/v1", tags=["project intelligence and personal workspace"])
MEMORY_TYPES = {"preference", "decision", "fact", "commitment", "workflow", "project_context"}
SECRET_TEXT = re.compile(r"(?i)(?:api[_-]?key|password|secret|token|authorization)\s*[:=]\s*\S+")


class MemoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: uuid.UUID | None = None
    memory_type: str = Field(min_length=1, max_length=24)
    title: str = Field(min_length=1, max_length=180)
    content: str = Field(min_length=1, max_length=5000)
    source: str = Field(min_length=1, max_length=240)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator("content")
    @classmethod
    def reject_secret_like_content(cls, value: str) -> str:
        if SECRET_TEXT.search(value):
            raise ValueError("Memory content appears to contain a secret")
        return value.strip()


class MemoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=180)
    content: str | None = Field(default=None, min_length=1, max_length=5000)
    archived: bool | None = None

    @field_validator("content")
    @classmethod
    def reject_secret_like_content(cls, value: str | None) -> str | None:
        if value and SECRET_TEXT.search(value):
            raise ValueError("Memory content appears to contain a secret")
        return value.strip() if value else value


class EnvironmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    surface: str = Field(min_length=1, max_length=60)
    item: str = Field(min_length=1, max_length=80)
    visibility: Literal["visible", "hidden", "minimized", "prioritized"]
    priority: int = Field(default=0, ge=-100, le=100)


class FocusCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: uuid.UUID
    objective: str = Field(min_length=1, max_length=500)
    duration_minutes: int = Field(ge=5, le=480)


class FocusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["pause", "resume", "complete", "cancel"]
    objective: str | None = Field(default=None, min_length=1, max_length=500)
    duration_minutes: int | None = Field(default=None, ge=5, le=480)


def _memory_view(row: Memory) -> dict[str, object]:
    return {"id": row.id, "project_id": row.project_id, "type": row.memory_type, "title": row.title,
            "content": row.content, "source": row.source, "confidence": row.confidence,
            "archived": row.archived, "metadata": row.metadata_json, "created_at": row.created_at,
            "updated_at": row.updated_at}


def _focus_view(row: FocusSession) -> dict[str, object]:
    started_at = row.started_at.replace(tzinfo=timezone.utc) if row.started_at.tzinfo is None else row.started_at
    ends_at = started_at + timedelta(minutes=row.duration_minutes)
    status = row.status
    if status == "active" and ends_at <= datetime.now(timezone.utc):
        status = "expired"
    return {"id": row.id, "project_id": row.project_id, "objective": row.objective,
            "duration_minutes": row.duration_minutes, "started_at": started_at,
            "ends_at": ends_at, "ended_at": row.ended_at, "status": status,
            "context_snapshot": row.context_snapshot}


def _expire_focus(row: FocusSession, now: datetime) -> None:
    started = row.started_at.replace(tzinfo=timezone.utc) if row.started_at.tzinfo is None else row.started_at
    if row.status == "active" and started + timedelta(minutes=row.duration_minutes) <= now:
        row.status = "expired"
        row.ended_at = now


def _own_project(session: Session, project_id: uuid.UUID, user_id: uuid.UUID) -> Project:
    project = ensure_project_access(session, project_id, user_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/projects/{project_id}/context")
def get_project_context(project_id: uuid.UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    project = _own_project(session, project_id, user.id)
    tasks = session.scalars(select(Task).where(Task.owner_id == user.id, Task.project_id == project.id).order_by(Task.updated_at.desc()).limit(100)).all()
    activities = session.scalars(select(Activity).where(Activity.user_id == user.id, Activity.project_id == project.id).order_by(Activity.created_at.desc()).limit(20)).all()
    memories = session.scalars(select(Memory).where(Memory.user_id == user.id, Memory.project_id == project.id, Memory.archived.is_(False)).order_by(Memory.updated_at.desc()).limit(20)).all()
    total = session.scalar(select(func.count(Task.id)).where(Task.owner_id == user.id, Task.project_id == project.id)) or 0
    done = session.scalar(select(func.count(Task.id)).where(Task.owner_id == user.id, Task.project_id == project.id, Task.status == TaskStatus.DONE)) or 0
    active_focus = session.scalar(select(FocusSession).where(FocusSession.user_id == user.id, FocusSession.project_id == project.id, FocusSession.status == "active").order_by(FocusSession.started_at.desc()))
    blockers = [task for task in tasks if task.status == TaskStatus.BLOCKED]
    unfinished = [task for task in tasks if task.status not in {TaskStatus.DONE, TaskStatus.CANCELLED}]
    return {
        "project": {"id": project.id, "name": project.name, "description": project.description,
                    "objective": project.objective, "status": project.status, "updated_at": project.updated_at},
        "progress": {"completed_tasks": done, "total_tasks": total, "percentage": round(done * 100 / total) if total else None},
        "tasks": [{"id": task.id, "title": task.title, "status": task.status, "priority": task.priority} for task in tasks[:30]],
        "next_actions": [{"id": task.id, "title": task.title, "status": task.status} for task in unfinished[:5]],
        "blockers": [{"id": task.id, "title": task.title} for task in blockers[:20]],
        "activity": [{"id": row.id, "summary": row.summary, "created_at": row.created_at, "result_status": row.result_status} for row in activities],
        "knowledge": [_memory_view(row) for row in memories if row.memory_type in {"decision", "fact", "project_context", "workflow"}],
        "active_focus": _focus_view(active_focus) if active_focus else None,
        "agents": [], "files": [],
    }


@router.get("/memories")
def list_memories(project_id: uuid.UUID | None = None, memory_type: str | None = None, search: str | None = Query(default=None, max_length=120), include_archived: bool = False, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict[str, object]]:
    statement = select(Memory).where(Memory.user_id == user.id)
    if project_id:
        _own_project(session, project_id, user.id)
        statement = statement.where(Memory.project_id == project_id)
    if memory_type:
        if memory_type not in MEMORY_TYPES:
            raise HTTPException(status_code=422, detail="Memory type is invalid")
        statement = statement.where(Memory.memory_type == memory_type)
    if not include_archived:
        statement = statement.where(Memory.archived.is_(False))
    if search:
        statement = statement.where(Memory.title.ilike(f"%{search}%") | Memory.content.ilike(f"%{search}%"))
    return [_memory_view(row) for row in session.scalars(statement.order_by(Memory.updated_at.desc()).limit(100)).all()]


@router.post("/memories", status_code=201)
def create_memory(data: MemoryCreate, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    if data.memory_type not in MEMORY_TYPES:
        raise HTTPException(status_code=422, detail="Memory type is invalid")
    if data.project_id:
        _own_project(session, data.project_id, user.id)
    row = Memory(user_id=user.id, **data.model_dump())
    session.add(row)
    session.flush()
    add_activity(session, user_id=user.id, actor_user_id=user.id, project_id=row.project_id, activity_type=ActivityType.MEMORY_CHANGED, summary=f"Saved memory: {row.title}")
    session.commit()
    session.refresh(row)
    return _memory_view(row)


@router.patch("/memories/{memory_id}")
def update_memory(memory_id: uuid.UUID, data: MemoryUpdate, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    row = session.scalar(select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(row, key, value)
    add_activity(session, user_id=user.id, actor_user_id=user.id, project_id=row.project_id, activity_type=ActivityType.MEMORY_CHANGED, summary=f"Updated memory: {row.title}")
    session.commit()
    session.refresh(row)
    return _memory_view(row)


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None)
def delete_memory(memory_id: uuid.UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> Response:
    row = session.scalar(select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    add_activity(session, user_id=user.id, actor_user_id=user.id, project_id=row.project_id, activity_type=ActivityType.MEMORY_CHANGED, summary=f"Deleted memory: {row.title}")
    session.delete(row)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/environment/preferences")
def list_environment_preferences(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict[str, object]]:
    return [{"surface": row.surface, "item": row.item, "visibility": row.visibility, "priority": row.priority, "source": row.source} for row in session.scalars(select(EnvironmentPreference).where(EnvironmentPreference.user_id == user.id)).all()]


@router.put("/environment/preferences")
def set_environment_preference(data: EnvironmentUpdate, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    if data.surface == "navigation":
        ensure_user_preferences(session, user)
        assignment = session.scalar(select(UserCapability).join(Capability, Capability.id == UserCapability.capability_id).where(UserCapability.user_id == user.id, Capability.code == data.item))
        if assignment is None:
            raise HTTPException(status_code=422, detail="Navigation item is not available")
        if not assignment.granted:
            raise HTTPException(status_code=403, detail="Navigation item is not granted")
        assignment.visible = data.visibility != "hidden"
        assignment.pinned = data.visibility == "prioritized" and assignment.visible
    row = session.scalar(select(EnvironmentPreference).where(EnvironmentPreference.user_id == user.id, EnvironmentPreference.surface == data.surface, EnvironmentPreference.item == data.item))
    if row is None:
        row = EnvironmentPreference(user_id=user.id, surface=data.surface, item=data.item)
        session.add(row)
    row.visibility, row.priority, row.source = data.visibility, data.priority, "explicit"
    session.commit()
    return {"surface": row.surface, "item": row.item, "visibility": row.visibility, "priority": row.priority, "source": row.source}


@router.delete("/environment/preferences", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None)
def reset_environment_preferences(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> Response:
    session.query(EnvironmentPreference).filter(EnvironmentPreference.user_id == user.id).delete(synchronize_session=False)
    assignments = session.scalars(select(UserCapability).where(UserCapability.user_id == user.id)).all()
    for assignment in assignments:
        capability = session.get(Capability, assignment.capability_id)
        assignment.visible = bool(assignment.granted and capability and capability.code in {"home", "tasks"})
        assignment.pinned = assignment.visible
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/focus-sessions")
def list_focus_sessions(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict[str, object]]:
    rows = session.scalars(select(FocusSession).where(FocusSession.user_id == user.id).order_by(FocusSession.started_at.desc()).limit(50)).all()
    now = datetime.now(timezone.utc)
    for row in rows:
        _expire_focus(row, now)
    session.commit()
    return [_focus_view(row) for row in rows]


@router.post("/focus-sessions", status_code=201)
def start_focus(data: FocusCreate, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    project = _own_project(session, data.project_id, user.id)
    now = datetime.now(timezone.utc)
    active = session.scalar(select(FocusSession).where(FocusSession.user_id == user.id, FocusSession.status == "active").with_for_update())
    if active:
        _expire_focus(active, now)
        if active.status == "active":
            active.status, active.ended_at = "completed", now
    context = {"project_name": project.name, "objective": project.objective}
    row = FocusSession(user_id=user.id, project_id=project.id, objective=data.objective.strip(), duration_minutes=data.duration_minutes, context_snapshot=context)
    session.add(row)
    session.flush()
    add_activity(session, user_id=user.id, actor_user_id=user.id, project_id=project.id, activity_type=ActivityType.FOCUS_UPDATED, summary=f"Started focus: {row.objective}")
    session.commit()
    session.refresh(row)
    return _focus_view(row)


@router.patch("/focus-sessions/{focus_id}")
def update_focus(focus_id: uuid.UUID, data: FocusUpdate, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    row = session.scalar(select(FocusSession).where(FocusSession.id == focus_id, FocusSession.user_id == user.id).with_for_update())
    if row is None:
        raise HTTPException(status_code=404, detail="Focus session not found")
    if row.status not in {"active", "paused"}:
        raise HTTPException(status_code=409, detail="Focus session has already ended")
    _expire_focus(row, datetime.now(timezone.utc))
    if row.status == "expired":
        session.commit()
        raise HTTPException(status_code=409, detail="Focus session has expired")
    if data.objective is not None:
        row.objective = data.objective.strip()
    if data.duration_minutes is not None:
        row.duration_minutes = data.duration_minutes
    if data.action == "pause":
        started_at = row.started_at.replace(tzinfo=timezone.utc) if row.started_at.tzinfo is None else row.started_at
        end = started_at + timedelta(minutes=row.duration_minutes)
        remaining = max(5, int((end - datetime.now(timezone.utc)).total_seconds() // 60))
        row.duration_minutes = remaining
        row.status = "paused"
    elif data.action == "resume":
        row.started_at = datetime.now(timezone.utc)
        row.status = "active"
    else:
        row.status = "completed" if data.action == "complete" else "cancelled"
        row.ended_at = datetime.now(timezone.utc)
    add_activity(session, user_id=user.id, actor_user_id=user.id, project_id=row.project_id, activity_type=ActivityType.FOCUS_UPDATED, summary=f"Focus session {row.status}: {row.objective}")
    session.commit()
    session.refresh(row)
    return _focus_view(row)
