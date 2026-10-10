"""Authenticated calendar event operations."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from typing_extensions import Annotated

from orin_api.auth import get_current_user
from orin_api.database import get_session
from orin_api.models import CalendarEvent, Project, ProjectMember, Task, TaskSchedule, TaskStatus, User
from orin_api.focus_domain import complete_task
from orin_api.models import ActivityType
from orin_api.services import add_activity

router = APIRouter(prefix="/api/v1/calendar", tags=["calendar"])
EventTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]


class EventWrite(BaseModel):
    title: EventTitle
    description: str | None = Field(default=None, max_length=10000)
    project_id: uuid.UUID | None = None
    is_all_day: bool = False
    start_at: datetime | None = None
    end_at: datetime | None = None
    start_date: date | None = None
    end_date: date | None = None
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    reminder_minutes: Literal[5, 10, 15, 30, 60] | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> EventWrite:
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        if self.is_all_day:
            if self.start_date is None or self.end_date is None or self.start_at is not None or self.end_at is not None:
                raise ValueError("All-day events require start_date and end_date only")
            if self.end_date < self.start_date:
                raise ValueError("end_date cannot be before start_date")
        else:
            if self.start_at is None or self.end_at is None or self.start_date is not None or self.end_date is not None:
                raise ValueError("Timed events require start_at and end_at only")
            if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
                raise ValueError("Timed event values must include a timezone offset")
            if self.end_at < self.start_at:
                raise ValueError("end_at cannot be before start_at")
        return self


class EventCreate(EventWrite):
    pass


class EventPatch(BaseModel):
    title: EventTitle | None = None
    description: str | None = Field(default=None, max_length=10000)
    project_id: uuid.UUID | None = None
    is_all_day: bool | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    start_date: date | None = None
    end_date: date | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    reminder_minutes: Literal[5, 10, 15, 30, 60] | None = None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID | None
    title: str
    description: str | None
    is_all_day: bool
    start_at: datetime | None
    end_at: datetime | None
    start_date: date | None
    end_date: date | None
    timezone: str
    reminder_minutes: int | None
    created_at: datetime
    updated_at: datetime


class TaskBlockWrite(BaseModel):
    start_at: datetime
    end_at: datetime
    estimated_minutes: int = Field(ge=1, le=1440)
    timezone: str = Field(min_length=1, max_length=64)
    allow_overlap: bool = False

    @model_validator(mode="after")
    def validate_range(self) -> TaskBlockWrite:
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None or self.end_at <= self.start_at:
            raise ValueError("A task block needs timezone-aware times and a positive duration")
        actual_minutes = (self.end_at - self.start_at).total_seconds() / 60
        if abs(actual_minutes - self.estimated_minutes) > 1:
            raise ValueError("Block duration must match estimated_minutes")
        return self


class TaskBlockRead(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    title: str
    description: str | None
    status: str
    project_id: uuid.UUID | None
    project_name: str | None
    estimated_minutes: int
    start_at: datetime
    end_at: datetime
    timezone: str


class TaskStatusUpdate(BaseModel):
    status: str = Field(pattern="^(todo|in_progress|blocked|done|cancelled)$")


def _read(row: CalendarEvent) -> EventRead:
    values: dict[str, Any] = {key: getattr(row, key) for key in EventRead.model_fields}
    for key in ("start_at", "end_at", "created_at", "updated_at"):
        value = values[key]
        if isinstance(value, datetime) and value.tzinfo is None:
            values[key] = value.replace(tzinfo=timezone.utc)
    return EventRead.model_validate(values)


def _check_project(session: Session, project_id: uuid.UUID | None, user_id: uuid.UUID) -> None:
    if project_id is None:
        return
    project = session.scalar(select(Project.id).where(Project.id == project_id, Project.owner_id == user_id))
    if project is None:
        member = session.scalar(select(ProjectMember.id).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user_id
        ))
        if member is None:
            raise HTTPException(status_code=404, detail="Project not found in your workspace.")


def _apply(row: CalendarEvent, data: EventWrite) -> None:
    row.title = data.title
    row.description = data.description
    row.project_id = data.project_id
    row.is_all_day = data.is_all_day
    row.timezone = data.timezone
    row.reminder_minutes = data.reminder_minutes
    if data.is_all_day:
        row.start_date, row.end_date = data.start_date, data.end_date
        row.start_at = row.end_at = None
    else:
        row.start_at = data.start_at.astimezone(timezone.utc)  # type: ignore[union-attr]
        row.end_at = data.end_at.astimezone(timezone.utc)  # type: ignore[union-attr]
        row.start_date = row.end_date = None


def _block_read(schedule: TaskSchedule, task: Task, project: Project | None) -> TaskBlockRead:
    start = schedule.start_at.replace(tzinfo=timezone.utc) if schedule.start_at.tzinfo is None else schedule.start_at
    end = schedule.end_at.replace(tzinfo=timezone.utc) if schedule.end_at.tzinfo is None else schedule.end_at
    return TaskBlockRead(id=schedule.id, task_id=task.id, title=task.title, description=task.description,
        status=task.status.value, project_id=task.project_id, project_name=project.name if project else None,
        estimated_minutes=schedule.estimated_minutes, start_at=start, end_at=end, timezone=schedule.timezone)


def _blocks_for_range(session: Session, user_id: uuid.UUID, start_at: datetime, end_at: datetime) -> list[TaskBlockRead]:
    rows = session.execute(
        select(TaskSchedule, Task, Project).join(Task, Task.id == TaskSchedule.task_id)
        .outerjoin(Project, Project.id == Task.project_id)
        .where(TaskSchedule.user_id == user_id, TaskSchedule.start_at < end_at, TaskSchedule.end_at > start_at)
        .order_by(TaskSchedule.start_at)
    ).all()
    return [_block_read(schedule, task, project) for schedule, task, project in rows]


def _find_conflicts(
    session: Session, user_id: uuid.UUID, task_id: uuid.UUID, start_at: datetime, end_at: datetime, zone: ZoneInfo
) -> list[dict[str, str]]:
    conflicts: list[dict[str, str]] = []
    other_blocks = session.execute(
        select(TaskSchedule, Task).join(Task, Task.id == TaskSchedule.task_id).where(
            TaskSchedule.user_id == user_id, TaskSchedule.task_id != task_id,
            TaskSchedule.start_at < end_at, TaskSchedule.end_at > start_at,
        )
    ).all()
    conflicts.extend({"type": "task", "id": str(schedule.id), "title": task.title,
        "start_at": schedule.start_at.isoformat(), "end_at": schedule.end_at.isoformat()}
        for schedule, task in other_blocks)
    local_start = start_at.astimezone(zone).date()
    local_end = end_at.astimezone(zone).date()
    events = session.scalars(select(CalendarEvent).where(
        CalendarEvent.user_id == user_id,
        or_(
            CalendarEvent.is_all_day.is_(True) & (CalendarEvent.start_date <= local_end) & (CalendarEvent.end_date >= local_start),
            CalendarEvent.is_all_day.is_(False) & (CalendarEvent.start_at < end_at) & (CalendarEvent.end_at > start_at),
        ),
    )).all()
    conflicts.extend({"type": "event", "id": str(event.id), "title": event.title,
        "start_at": event.start_at.isoformat() if event.start_at else str(event.start_date),
        "end_at": event.end_at.isoformat() if event.end_at else str(event.end_date)} for event in events)
    return conflicts


@router.get("/schedule", response_model=list[TaskBlockRead])
def list_schedule(
    start: date,
    end: date,
    timezone_name: str = Query(default="UTC", alias="timezone", min_length=1, max_length=64),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[TaskBlockRead]:
    if end < start or (end - start).days > 366:
        raise HTTPException(status_code=422, detail="Choose a date range of at most 367 days.")
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="timezone must be a valid IANA timezone") from exc
    start_at = datetime.combine(start, time.min, zone).astimezone(timezone.utc)
    end_at = datetime.combine(end + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
    return _blocks_for_range(session, user.id, start_at, end_at)


@router.put("/tasks/{task_id}/schedule", response_model=TaskBlockRead)
def schedule_task(
    task_id: uuid.UUID,
    data: TaskBlockWrite,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TaskBlockRead:
    task = session.scalar(select(Task).where(Task.id == task_id, Task.owner_id == user.id).with_for_update())
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task.status in {TaskStatus.DONE, TaskStatus.CANCELLED}:
        raise HTTPException(status_code=409, detail="Closed tasks cannot be scheduled.")
    try:
        zone = ZoneInfo(data.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="timezone must be a valid IANA timezone") from exc
    start_at, end_at = data.start_at.astimezone(timezone.utc), data.end_at.astimezone(timezone.utc)
    conflicts = _find_conflicts(session, user.id, task.id, start_at, end_at, zone)
    if conflicts and not data.allow_overlap:
        raise HTTPException(status_code=409, detail={"message": "This time overlaps with existing commitments.", "conflicts": conflicts})
    row = session.scalar(select(TaskSchedule).where(TaskSchedule.task_id == task.id).with_for_update())
    if row is None:
        row = TaskSchedule(user_id=user.id, task_id=task.id, start_at=start_at, end_at=end_at,
            estimated_minutes=data.estimated_minutes, timezone=data.timezone)
        session.add(row)
    else:
        row.start_at, row.end_at = start_at, end_at
        row.estimated_minutes, row.timezone = data.estimated_minutes, data.timezone
    if task.estimated_minutes is None:
        task.estimated_minutes = data.estimated_minutes
    session.flush()
    add_activity(session, user_id=user.id, actor_user_id=user.id, task_id=task.id, project_id=task.project_id,
        activity_type=ActivityType.TASK_UPDATED, summary=f"Scheduled task: {task.title}")
    session.commit()
    session.refresh(row)
    return _block_read(row, task, task.project)


@router.delete("/tasks/{task_id}/schedule", status_code=status.HTTP_204_NO_CONTENT)
def unschedule_task(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    row = session.scalar(select(TaskSchedule).join(Task, Task.id == TaskSchedule.task_id).where(
        TaskSchedule.task_id == task_id, TaskSchedule.user_id == user.id, Task.owner_id == user.id,
    ))
    if row is None:
        raise HTTPException(status_code=404, detail="Scheduled task not found.")
    session.delete(row)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/events", response_model=list[EventRead])
def list_events(
    start: date,
    end: date,
    timezone_name: str = Query(default="UTC", alias="timezone", min_length=1, max_length=64),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[EventRead]:
    if end < start or (end - start).days > 366:
        raise HTTPException(status_code=422, detail="Choose a date range of at most 367 days.")
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="timezone must be a valid IANA timezone") from exc
    range_start = datetime.combine(start, time.min, zone).astimezone(timezone.utc)
    range_end = datetime.combine(end + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
    rows = session.scalars(select(CalendarEvent).where(
        CalendarEvent.user_id == user.id,
        or_(
            (CalendarEvent.is_all_day.is_(True) & (CalendarEvent.start_date <= end) & (CalendarEvent.end_date >= start)),
            (CalendarEvent.is_all_day.is_(False) & (CalendarEvent.start_at < range_end) & (CalendarEvent.end_at > range_start)),
        ),
    ).order_by(CalendarEvent.is_all_day.desc(), CalendarEvent.start_date, CalendarEvent.start_at)).all()
    return [_read(row) for row in rows]


@router.post("/events", response_model=EventRead, status_code=status.HTTP_201_CREATED)
def create_event(
    data: EventCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> EventRead:
    _check_project(session, data.project_id, user.id)
    row = CalendarEvent(user_id=user.id, title=data.title, is_all_day=data.is_all_day, timezone=data.timezone)
    _apply(row, data)
    session.add(row)
    session.commit()
    session.refresh(row)
    return _read(row)


@router.patch("/events/{event_id}", response_model=EventRead)
def update_event(
    event_id: uuid.UUID,
    changes: EventPatch,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> EventRead:
    row = session.scalar(select(CalendarEvent).where(CalendarEvent.id == event_id, CalendarEvent.user_id == user.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Calendar event not found.")
    values = {key: getattr(row, key) for key in EventWrite.model_fields}
    for key in ("start_at", "end_at"):
        if isinstance(values[key], datetime) and values[key].tzinfo is None:
            values[key] = values[key].replace(tzinfo=timezone.utc)
    values.update(changes.model_dump(exclude_unset=True))
    try:
        data = EventWrite.model_validate(values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Event details are invalid.") from exc
    _check_project(session, data.project_id, user.id)
    _apply(row, data)
    session.commit()
    session.refresh(row)
    return _read(row)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    event_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    row = session.scalar(select(CalendarEvent).where(CalendarEvent.id == event_id, CalendarEvent.user_id == user.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Calendar event not found.")
    session.delete(row)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
