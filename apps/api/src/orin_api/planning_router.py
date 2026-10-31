"""Private opportunities, risk register and recurring routines."""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from orin_api.auth import get_current_user
from orin_api.database import get_session
from orin_api.models import (
    Opportunity,
    Risk,
    Routine,
    RoutineCheckin,
    Project,
    Task,
    TaskStatus,
    User,
    ActivityType,
    Workspace,
)
from orin_api.planning_domain import occurrence, dates
from orin_api.services import add_activity

router = APIRouter(prefix="/api/v1", tags=["planning"])


def workspace_for_request(session: Session, user: User, workspace_id: uuid.UUID | None) -> Workspace:
    if workspace_id is not None:
        workspace = session.scalar(select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == user.id))
        if workspace is None:
            raise HTTPException(404, "Workspace not found")
        return workspace
    workspace_query = select(Workspace).where(Workspace.owner_id == user.id).order_by(Workspace.created_at.asc())
    workspace = session.scalar(workspace_query)
    if workspace is None:
        try:
            with session.begin_nested():
                workspace = Workspace(owner_id=user.id, name="Personal", color="#6b73ff")
                session.add(workspace)
                session.flush()
        except IntegrityError:
            workspace = session.scalar(workspace_query)
            if workspace is None:
                raise
    return workspace


class Write(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OpportunityWrite(Write):
    title: str = Field(min_length=1, max_length=240)
    project_id: uuid.UUID | None = None
    category: Literal[
        "job", "business", "learning", "creative", "ministry", "other"
    ] = "other"
    stage: Literal["inbox", "exploring", "pursuing", "waiting", "won", "closed"] = (
        "inbox"
    )
    description: str = Field(default="", max_length=10000)
    source_url: str = Field(default="", max_length=2000)
    contact: str = Field(default="", max_length=240)
    next_action: str = Field(default="", max_length=240)
    decision_notes: str = Field(default="", max_length=10000)
    deadline: date | None = None
    review_on: date | None = None
    value: int = Field(default=3, ge=1, le=5)
    fit: int = Field(default=3, ge=1, le=5)
    effort: int = Field(default=3, ge=1, le=5)

    @field_validator("source_url")
    @classmethod
    def safe_url(cls, value):
        if value and not value.startswith(("https://", "http://")):
            raise ValueError("Use an HTTP or HTTPS link")
        return value


class OpportunityRead(OpportunityWrite):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    task_id: uuid.UUID | None


class RiskWrite(Write):
    title: str = Field(min_length=1, max_length=240)
    opportunity_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    likelihood: int = Field(default=3, ge=1, le=5)
    impact: int = Field(default=3, ge=1, le=5)
    status: Literal["open", "watching", "resolved", "occurred"] = "open"
    response: Literal["reduce", "avoid", "accept", "transfer"] = "reduce"
    trigger: str = Field(default="", max_length=500)
    mitigation: str = Field(default="", max_length=10000)
    review_on: date | None = None


class RiskRead(RiskWrite):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class RoutineWrite(Write):
    title: str = Field(min_length=1, max_length=240)
    timezone: str = Field(default="UTC", max_length=64)
    weekdays: list[int] = Field(
        default_factory=lambda: list(range(7)), min_length=1, max_length=7
    )
    start_date: date
    end_date: date | None = None
    time_of_day: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    duration_minutes: int = Field(default=15, ge=1, le=240)
    minimum_minutes: int = Field(default=2, ge=1, le=240)
    cue: str = Field(default="", max_length=500)
    steps: str = Field(default="", max_length=2000)
    minimum_action: str = Field(default="", max_length=500)
    reward: str = Field(default="", max_length=500)
    reminder_minutes: Literal[0, 5, 10, 15, 30] | None = None
    paused: bool = False

    @model_validator(mode="after")
    def validate_schedule(self):
        try:
            ZoneInfo(self.timezone)
        except (KeyError, ValueError):
            raise ValueError("Use a valid IANA timezone")
        if any(day not in range(7) for day in self.weekdays) or len(
            set(self.weekdays)
        ) != len(self.weekdays):
            raise ValueError("Use distinct weekdays from 0 to 6")
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("End date must follow start date")
        if self.minimum_minutes > self.duration_minutes:
            raise ValueError("Minimum duration must fit within full duration")
        return self


class RoutineRead(RoutineWrite):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class CheckinWrite(Write):
    status: Literal["done", "minimum", "skipped"]


def owned(session, model, item_id, user, lock=False):
    query = select(model).where(model.id == item_id, model.user_id == user.id)
    row = session.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise HTTPException(404, "Record not found")
    return row


def references(session, data, user):
    if data.project_id:
        project = session.get(Project, data.project_id)
        if not project or project.owner_id != user.id:
            raise HTTPException(404, "Project not found")
    if isinstance(data, RiskWrite) and data.opportunity_id:
        owned(session, Opportunity, data.opportunity_id, user)


def list_owned(model, session, user, offset, limit):
    return session.scalars(
        select(model)
        .where(model.user_id == user.id)
        .order_by(model.created_at.desc(), model.id)
        .offset(offset)
        .limit(limit)
    ).all()


@router.get("/opportunities", response_model=list[OpportunityRead])
def opportunities(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    return list_owned(Opportunity, session, user, offset, limit)


@router.post("/opportunities", response_model=OpportunityRead, status_code=201)
def create_opportunity(
    data: OpportunityWrite,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    references(session, data, user)
    row = Opportunity(user_id=user.id, **data.model_dump())
    session.add(row)
    session.commit()
    return row


@router.put("/opportunities/{item_id}", response_model=OpportunityRead)
def update_opportunity(
    item_id: uuid.UUID,
    data: OpportunityWrite,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    row = owned(session, Opportunity, item_id, user, True)
    references(session, data, user)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    session.commit()
    return row


@router.post("/opportunities/{item_id}/next-task")
def next_task(
    item_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    row = owned(session, Opportunity, item_id, user, True)
    if not row.next_action:
        raise HTTPException(422, "Add a small next action first")
    existing_task = session.get(Task, row.task_id) if row.task_id else None
    if existing_task is None or existing_task.status in {
        TaskStatus.DONE,
        TaskStatus.CANCELLED,
    }:
        task = Task(
            owner_id=user.id,
            project_id=row.project_id,
            title=row.next_action,
            first_step=row.next_action,
            why=row.title,
        )
        session.add(task)
        session.flush()
        row.task_id = task.id
        add_activity(
            session,
            user_id=user.id,
            actor_user_id=user.id,
            project_id=task.project_id,
            task_id=task.id,
            activity_type=ActivityType.TASK_CREATED,
            summary=f"Created opportunity next action: {task.title}",
        )
    session.commit()
    return {"task_id": row.task_id}


@router.get("/risks", response_model=list[RiskRead])
def risks(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    return list_owned(Risk, session, user, offset, limit)


@router.post("/risks", response_model=RiskRead, status_code=201)
def create_risk(
    data: RiskWrite,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    references(session, data, user)
    row = Risk(user_id=user.id, **data.model_dump())
    session.add(row)
    session.commit()
    return row


@router.put("/risks/{item_id}", response_model=RiskRead)
def update_risk(
    item_id: uuid.UUID,
    data: RiskWrite,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    row = owned(session, Risk, item_id, user, True)
    references(session, data, user)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    session.commit()
    return row


@router.get("/calendar/routines", response_model=list[RoutineRead])
def routines(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID | None = Header(default=None, alias="X-Orin-Workspace-Id"),
):
    workspace = workspace_for_request(session, user, workspace_id)
    return list(session.scalars(select(Routine).where(Routine.user_id == user.id, Routine.workspace_id == workspace.id).order_by(Routine.created_at.desc()).offset(offset).limit(limit)).all())


@router.post("/calendar/routines", response_model=RoutineRead, status_code=201)
def create_routine(
    data: RoutineWrite,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID | None = Header(default=None, alias="X-Orin-Workspace-Id"),
):
    workspace = workspace_for_request(session, user, workspace_id)
    row = Routine(user_id=user.id, workspace_id=workspace.id, **data.model_dump())
    session.add(row)
    session.commit()
    return row


@router.put("/calendar/routines/{item_id}", response_model=RoutineRead)
def update_routine(
    item_id: uuid.UUID,
    data: RoutineWrite,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    row = owned(session, Routine, item_id, user, True)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    session.commit()
    return row


@router.get("/calendar/routine-occurrences")
def routine_occurrences(
    start: date,
    end: date,
    display_timezone: str | None = Query(None, alias="timezone"),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID | None = Header(default=None, alias="X-Orin-Workspace-Id"),
):
    if not 0 <= (end - start).days <= 92:
        raise HTTPException(422, "Choose a range of up to 93 days")
    try:
        display_zone = ZoneInfo(display_timezone) if display_timezone else None
    except (KeyError, ValueError):
        raise HTTPException(422, "Use a valid display timezone")
    workspace = workspace_for_request(session, user, workspace_id)
    rows = session.scalars(
        select(Routine).where(Routine.user_id == user.id, Routine.workspace_id == workspace.id, Routine.paused.is_(False))
    ).all()
    checkins = {
        (c.routine_id, c.day): c.status
        for c in session.scalars(
            select(RoutineCheckin).where(
                RoutineCheckin.user_id == user.id,
                RoutineCheckin.day.between(
                    start - timedelta(days=1), end + timedelta(days=1)
                ),
            )
        )
    }
    result = []
    for routine in rows:
        for day in dates(
            start - timedelta(days=1) if display_zone else start,
            end + timedelta(days=1) if display_zone else end,
        ):
            instant = occurrence(routine, day)
            if instant and (
                display_zone is None
                or start <= instant.astimezone(display_zone).date() <= end
            ):
                result.append(
                    {
                        "routine_id": routine.id,
                        "day": day,
                        "title": routine.title,
                        "start_at": instant,
                        "end_at": instant + timedelta(minutes=routine.duration_minutes),
                        "status": checkins.get((routine.id, day), "pending"),
                        "cue": routine.cue,
                        "minimum_action": routine.minimum_action,
                        "duration_minutes": routine.duration_minutes,
                        "minimum_minutes": routine.minimum_minutes,
                    }
                )
    return sorted(result, key=lambda r: (r["start_at"], str(r["routine_id"])))


@router.put("/calendar/routines/{item_id}/checkins/{day}")
def checkin(
    item_id: uuid.UUID,
    day: date,
    data: CheckinWrite,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    routine = owned(session, Routine, item_id, user, True)
    if (
        day > datetime.now(ZoneInfo(routine.timezone)).date()
        or occurrence(routine, day) is None
    ):
        raise HTTPException(422, "Check in on a scheduled day, today or earlier")
    row = session.scalar(
        select(RoutineCheckin).where(
            RoutineCheckin.routine_id == item_id, RoutineCheckin.day == day
        )
    )
    if row is None:
        row = RoutineCheckin(user_id=user.id, routine_id=item_id, day=day)
        session.add(row)
    row.status = data.status
    session.commit()
    return {"status": row.status}


@router.delete("/calendar/routines/{item_id}/checkins/{day}", status_code=204)
def undo_checkin(
    item_id: uuid.UUID,
    day: date,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    owned(session, Routine, item_id, user, True)
    row = session.scalar(
        select(RoutineCheckin).where(
            RoutineCheckin.routine_id == item_id, RoutineCheckin.day == day
        )
    )
    if row:
        session.delete(row)
    session.commit()
    return Response(status_code=204)


# Explicit, owner-scoped deletion keeps lifecycle behavior consistent with account export/deletion.
def register_delete(path, model):
    def remove(
        item_id: uuid.UUID,
        session: Session = Depends(get_session),
        user: User = Depends(get_current_user),
    ):
        session.delete(owned(session, model, item_id, user, True))
        session.commit()
        return Response(status_code=204)

    router.add_api_route(
        path + "/{item_id}",
        remove,
        methods=["DELETE"],
        status_code=204,
        name="delete_" + model.__tablename__,
    )


for path, model in (
    ("/opportunities", Opportunity),
    ("/risks", Risk),
    ("/calendar/routines", Routine),
):
    register_delete(path, model)
