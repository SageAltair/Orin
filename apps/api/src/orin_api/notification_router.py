"""Owner-scoped notification inbox, explicit consent and reversible follow-up controls."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from orin_api.auth import get_current_user
from orin_api.database import get_session
from orin_api.models import Notification, User
from orin_api.notifications import (
    policy,
    attention_allowed,
    category_enabled,
    CATEGORIES,
    relevant,
    utc,
)

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    enabled: bool = True
    categories: list[
        Literal[
            "calendar",
            "routines",
            "tasks",
            "projects",
            "opportunities",
            "risks",
            "approvals",
            "jobs",
            "writing",
        ]
    ] = Field(default_factory=lambda: list(CATEGORIES), max_length=9)
    persistent: bool = False
    repeat_minutes: Literal[5, 15, 30, 60] = 15
    max_repeats: int = Field(default=3, ge=1, le=5)
    timezone: str = Field(default="UTC", max_length=64)
    quiet_enabled: bool = False
    quiet_start: str = Field(default="22:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    quiet_end: str = Field(default="07:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    respect_focus: bool = True
    browser_alerts: bool = False
    sound: bool = False

    @model_validator(mode="after")
    def validate_timezone(self):
        try:
            ZoneInfo(self.timezone)
        except (KeyError, ValueError):
            raise ValueError("Use a valid IANA timezone")
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("Categories must be distinct")
        return self


@router.get("/preferences", response_model=Preferences)
def preferences(
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    row = policy(session, user.id)
    try:
        result = Preferences.model_validate(row)
    except ValidationError:
        # Legacy database rows may predate validation (or contain corrupt JSON).
        # Return a conservative, non-delivering projection so settings can load
        # and be explicitly repaired. Never silently rewrite persisted consent.
        result = Preferences(
            enabled=False,
            categories=[],
            persistent=False,
            browser_alerts=False,
            sound=False,
        )
        response.headers["X-Orin-Preferences-Recovery"] = "required"
    session.commit()
    return result


@router.put("/preferences", response_model=Preferences)
def update_preferences(
    data: Preferences,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    row = policy(session, user.id)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    session.commit()
    return row


class NotificationRead(BaseModel):
    id: uuid.UUID
    title: str
    message: str
    event_id: uuid.UUID | None
    source_id: uuid.UUID | None
    category: str
    due_at: datetime
    read_at: datetime | None
    snoozed_until: datetime | None
    revision: int
    repeats: int
    attention_ready: bool


@router.get("", response_model=list[NotificationRead])
def list_notifications(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    prefs = policy(session, user.id)
    now = datetime.now(timezone.utc)
    allowed = attention_allowed(session, prefs, now)
    rows = session.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.due_at.desc(), Notification.id)
        .offset(offset)
        .limit(limit)
    ).all()
    result = []
    for row in rows:
        if row.read_at is None and (
            not relevant(session, row)
            or (
                row.category in {"calendar", "routines"}
                and utc(row.due_at) + timedelta(hours=2) < now
            )
        ):
            row.read_at = now
        lead = (
            10
            if row.delivery_key.startswith("task-block:")
            else (
                30
                if row.category == "tasks" and row.delivery_key.startswith("task:")
                else 0
            )
        )
        ready = bool(
            allowed
            and category_enabled(prefs, row.category)
            and row.read_at is None
            and now >= utc(row.due_at) - timedelta(minutes=lead)
            and (row.snoozed_until is None or utc(row.snoozed_until) <= now)
        )
        if ready and row.attention_at is None:
            row.attention_at = now
        result.append(
            {
                "id": row.id,
                "title": row.title,
                "message": row.message,
                "event_id": row.event_id,
                "source_id": row.source_id,
                "category": row.category,
                "due_at": utc(row.due_at),
                "read_at": utc(row.read_at) if row.read_at else None,
                "snoozed_until": utc(row.snoozed_until) if row.snoozed_until else None,
                "revision": row.revision,
                "repeats": row.repeats,
                "attention_ready": ready,
            }
        )
    session.commit()
    return result


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["acknowledge", "snooze"]
    minutes: Literal[5, 15, 60, 1440] = 15


@router.post("/{notification_id}/action")
def notification_action(
    notification_id: uuid.UUID,
    data: Action,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    row = session.scalar(
        select(Notification)
        .where(Notification.id == notification_id, Notification.user_id == user.id)
        .with_for_update()
    )
    if row is None:
        raise HTTPException(404, "Reminder not found")
    now = datetime.now(timezone.utc)
    if data.action == "acknowledge":
        row.read_at = now
    else:
        row.snoozed_until = now + timedelta(minutes=data.minutes)
        row.attention_at = None
        row.read_at = None
        row.revision += 1
    session.commit()
    return {"status": data.action}


@router.patch("/{notification_id}/read")
def read_notification(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    notification_action(notification_id, Action(action="acknowledge"), user, session)
    return {"status": "read"}
