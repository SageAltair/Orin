"""Authenticated, ownership-scoped persistence for focus data."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from orin_api.auth import get_current_user
from orin_api.database import get_session
from orin_api.focus_domain import complete_task, local_day_key, set_focus_state, touch_task
from orin_api.focus_planning import select_now_task, select_todays_three, task_rank
from orin_api.models import DailyClose, DailyPlan, DailyPlanTask, DriftEvent, DriftTrigger, EnergyLevel, FocusSession, FocusState, Task, TaskStatus, User, UserSettings

router = APIRouter(prefix="/api/v1/focus", tags=["focus"])


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    energy_today: EnergyLevel | None = None
    preferred_anchor_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    quiet_hours: dict[str, str] | None = None
    reduced_motion: bool | None = None
    hide_timer_numbers: bool | None = None
    sound_enabled: bool | None = None
    haptics_enabled: bool | None = None
    theme: Literal["light", "dark", "auto"] | None = None
    body_doubling_enabled: bool | None = None
    accountability_contact: str | None = Field(default=None, max_length=240)


class DriftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: uuid.UUID | None = None
    focus_session_id: uuid.UUID | None = None
    trigger_type: DriftTrigger
    note: str | None = Field(default=None, max_length=4000)


class DailyCloseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    done_list: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    drift_summary: str | None = Field(default=None, max_length=4000)
    tomorrow_task_id: uuid.UUID | None = None
    reflection: str | None = Field(default=None, max_length=4000)
    drift_triggers: list[DriftTrigger] = Field(default_factory=list, max_length=6)


class CaptureCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=240)


class EnergyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    energy_level: EnergyLevel


class TodayTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: uuid.UUID
    is_anchor: bool = False


class TodayPlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tasks: list[TodayTaskInput] = Field(max_length=3)


class SwapInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: uuid.UUID | None = None


def _day(now: datetime, timezone_name: str) -> str:
    try:
        ZoneInfo(timezone_name)
        return local_day_key(now, timezone_name)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise HTTPException(status_code=422, detail="Timezone must be a valid IANA timezone") from exc


def _settings_row(session: Session, user_id: uuid.UUID) -> UserSettings:
    row = session.scalar(select(UserSettings).where(UserSettings.user_id == user_id))
    if row is None:
        row = UserSettings(user_id=user_id)
        session.add(row)
        session.flush()
    return row


def _settings_view(row: UserSettings) -> dict[str, object]:
    return {"timezone": row.timezone, "day_key": row.day_key, "energy_today": row.energy_today.value if row.energy_today else None,
            "preferred_anchor_time": row.preferred_anchor_time, "quiet_hours": row.quiet_hours,
            "reduced_motion": row.reduced_motion, "sound_enabled": row.sound_enabled,
            "hide_timer_numbers": row.hide_timer_numbers,
            "haptics_enabled": row.haptics_enabled, "theme": row.theme,
            "body_doubling_enabled": row.body_doubling_enabled, "accountability_contact": row.accountability_contact}


def _today_context(session: Session, user: User) -> tuple[UserSettings, str, DailyPlan | None]:
    settings_row = _settings_row(session, user.id)
    day_key = _day(datetime.now(timezone.utc), settings_row.timezone)
    if settings_row.day_key != day_key:
        settings_row.day_key, settings_row.energy_today = day_key, None
    plan = session.scalar(select(DailyPlan).where(DailyPlan.user_id == user.id, DailyPlan.day_key == day_key))
    return settings_row, day_key, plan


def _get_or_create_plan(session: Session, user: User) -> tuple[UserSettings, str, DailyPlan]:
    settings_row, day_key, plan = _today_context(session, user)
    if plan is None:
        plan = DailyPlan(user_id=user.id, day_key=day_key, energy_level=settings_row.energy_today)
        session.add(plan)
        session.flush()
    return settings_row, day_key, plan


def _task_view(task: Task) -> dict[str, object]:
    return {"id": task.id, "title": task.title, "description": task.description, "status": task.status.value,
            "focus_state": task.focus_state.value if task.focus_state else None, "first_step": task.first_step,
            "why": task.why, "energy_level": task.energy_level.value if task.energy_level else None,
            "estimated_minutes": task.estimated_minutes, "is_anchor": task.is_anchor,
            "today_position": task.today_position, "today_day_key": task.today_day_key,
            "last_touched_at": task.last_touched_at, "completed_at": task.completed_at,
            "released_at": task.released_at, "project_id": task.project_id}


def _assignments(session: Session, user: User, plan: DailyPlan) -> list[tuple[Task, bool, int]]:
    rows = session.execute(select(Task, DailyPlanTask.is_anchor, DailyPlanTask.position)
        .join(DailyPlanTask, DailyPlanTask.task_id == Task.id)
        .where(DailyPlanTask.user_id == user.id, DailyPlanTask.plan_id == plan.id, Task.owner_id == user.id)
        .order_by(DailyPlanTask.position)).all()
    return [(task, is_anchor, position) for task, is_anchor, position in rows]


def _plan_view(session: Session, user: User, plan: DailyPlan | None, day_key: str,
               energy: EnergyLevel | None) -> dict[str, object]:
    assigned = _assignments(session, user, plan) if plan else []
    return {"day_key": day_key, "energy_level": (plan.energy_level.value if plan and plan.energy_level else energy.value if energy else None),
            "tasks": [{**_task_view(task), "is_anchor": anchor, "today_position": position}
                      for task, anchor, position in assigned]}


def _replace_plan(session: Session, user: User, plan: DailyPlan, day_key: str,
                  items: list[TodayTaskInput]) -> None:
    if len({item.task_id for item in items}) != len(items):
        raise HTTPException(status_code=422, detail="A task can appear only once in Today's Three")
    if sum(item.is_anchor for item in items) > 1:
        raise HTTPException(status_code=422, detail="Today's Three can have at most one anchor")
    ids = [item.task_id for item in items]
    tasks = session.scalars(select(Task).where(Task.owner_id == user.id, Task.id.in_(ids))).all() if ids else []
    by_id = {task.id: task for task in tasks}
    if len(by_id) != len(ids):
        raise HTTPException(status_code=404, detail="One or more tasks are not available")
    if any(task.status in {TaskStatus.DONE, TaskStatus.CANCELLED} for task in tasks):
        raise HTTPException(status_code=409, detail="Completed or released tasks cannot be added to Today")
    previous = _assignments(session, user, plan)
    keep = set(ids)
    for task, _, _ in previous:
        if task.id not in keep and task.status not in {TaskStatus.DONE, TaskStatus.CANCELLED}:
            set_focus_state(task, FocusState.LATER)
            task.today_day_key, task.today_position, task.is_anchor = None, None, False
    session.execute(delete(DailyPlanTask).where(DailyPlanTask.user_id == user.id, DailyPlanTask.plan_id == plan.id))
    session.flush()
    for position, item in enumerate(items):
        task = by_id[item.task_id]
        set_focus_state(task, FocusState.TODAY)
        task.today_day_key, task.today_position, task.is_anchor = day_key, position, item.is_anchor
        session.add(DailyPlanTask(user_id=user.id, plan_id=plan.id, task_id=task.id,
                                  position=position, is_anchor=item.is_anchor))


def _current_now(session: Session, user: User) -> tuple[Task | None, FocusSession | None, str, EnergyLevel | None, DailyPlan | None]:
    settings_row, day_key, plan = _today_context(session, user)
    now = datetime.now(timezone.utc)
    active_session = session.scalar(select(FocusSession).join(Task, Task.id == FocusSession.task_id)
        .where(FocusSession.user_id == user.id, FocusSession.status == "active", Task.owner_id == user.id,
               Task.status.not_in([TaskStatus.DONE, TaskStatus.CANCELLED]))
        .order_by(FocusSession.started_at.desc()).limit(1))
    if active_session:
        from orin_api.workspace_router import _expire_focus
        _expire_focus(active_session, now)
        if active_session.status == "active":
            task = session.scalar(select(Task).where(Task.id == active_session.task_id, Task.owner_id == user.id))
            return task, active_session, day_key, settings_row.energy_today, plan
    assigned = _assignments(session, user, plan) if plan else []
    return select_now_task(None, assigned), None, day_key, settings_row.energy_today, plan


def _now_view(task: Task | None, focus: FocusSession | None, day_key: str,
              energy: EnergyLevel | None) -> dict[str, object]:
    return {"task": _task_view(task) if task else None,
            "focus_session": ({"id": focus.id, "task_id": focus.task_id, "duration_minutes": focus.duration_minutes,
                               "started_at": focus.started_at, "status": focus.status} if focus else None),
            "day_key": day_key, "energy_level": energy.value if energy else None,
            "empty_state": task is None}


@router.post("/capture", status_code=status.HTTP_201_CREATED)
def capture_task(data: CaptureCreate = CaptureCreate(), user: User = Depends(get_current_user),
                 session: Session = Depends(get_session)) -> dict[str, object]:
    title = (data.title or "").strip() or "Untitled task"
    task = Task(owner_id=user.id, title=title, status=TaskStatus.TODO, focus_state=FocusState.INBOX)
    touch_task(task)
    session.add(task)
    session.commit()
    session.refresh(task)
    return _task_view(task)


@router.put("/energy")
def set_energy(data: EnergyUpdate, user: User = Depends(get_current_user),
               session: Session = Depends(get_session)) -> dict[str, object]:
    settings_row, day_key, plan = _today_context(session, user)
    settings_row.day_key, settings_row.energy_today = day_key, data.energy_level
    if plan:
        plan.energy_level = data.energy_level
    session.commit()
    return {"day_key": day_key, "energy_level": data.energy_level.value}


@router.get("/today")
def get_today(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    settings_row, day_key, plan = _today_context(session, user)
    response = _plan_view(session, user, plan, day_key, settings_row.energy_today)
    session.commit()
    return response


@router.post("/today/propose")
def propose_today(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    settings_row, day_key, plan = _get_or_create_plan(session, user)
    if settings_row.energy_today is None:
        session.commit()
        raise HTTPException(status_code=409, detail="Choose today's energy before selecting tasks")
    if not _assignments(session, user, plan):
        excluded: set[uuid.UUID] = set()
        for raw_id in plan.swapped_task_ids:
            try:
                excluded.add(uuid.UUID(raw_id))
            except ValueError:
                continue
        candidates = session.scalars(select(Task).where(Task.owner_id == user.id,
            Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED]),
            Task.focus_state.in_([FocusState.INBOX, FocusState.LATER]))).all()
        selected, anchor_id = select_todays_three(candidates, settings_row.energy_today, excluded_ids=excluded)
        _replace_plan(session, user, plan, day_key,
                      [TodayTaskInput(task_id=task.id, is_anchor=task.id == anchor_id) for task in selected])
    response = _plan_view(session, user, plan, day_key, settings_row.energy_today)
    session.commit()
    return response


@router.put("/today/tasks")
def replace_today(data: TodayPlanInput, user: User = Depends(get_current_user),
                  session: Session = Depends(get_session)) -> dict[str, object]:
    settings_row, day_key, plan = _get_or_create_plan(session, user)
    _replace_plan(session, user, plan, day_key, data.tasks)
    response = _plan_view(session, user, plan, day_key, settings_row.energy_today)
    session.commit()
    return response


@router.get("/now")
def get_now(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    task, focus, day_key, energy, _ = _current_now(session, user)
    response = _now_view(task, focus, day_key, energy)
    session.commit()
    return response


@router.post("/now/start")
def start_now(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    task, _, _, _, _ = _current_now(session, user)
    if task is None:
        raise HTTPException(status_code=409, detail="There is no task selected for Now")
    from orin_api.workspace_router import FocusCreate, start_focus
    minutes = task.estimated_minutes or 25
    result = start_focus(FocusCreate(project_id=task.project_id, task_id=task.id,
                         objective=task.title, duration_minutes=min(max(minutes, 5), 480)), user, session)
    set_focus_state(task, FocusState.ACTIVE)
    session.commit()
    return {"task": _task_view(task), "focus_session": result}


@router.post("/now/complete")
def complete_now(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    task, _, _, _, _ = _current_now(session, user)
    if task is None:
        raise HTTPException(status_code=409, detail="There is no task selected for Now")
    complete_task(task)
    now = datetime.now(timezone.utc)
    active = session.scalars(select(FocusSession).where(FocusSession.user_id == user.id,
        FocusSession.task_id == task.id, FocusSession.status.in_(["active", "paused"]))).all()
    for focus in active:
        focus.status, focus.ended_at = "completed", now
    next_task, focus, day_key, energy, _ = _current_now(session, user)
    response = _now_view(next_task, focus, day_key, energy)
    session.commit()
    return response


@router.get("/later")
def get_later(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict[str, object]]:
    tasks = session.scalars(select(Task).where(Task.owner_id == user.id,
        Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED]),
        Task.focus_state.in_([FocusState.INBOX, FocusState.LATER]))).all()
    return [_task_view(task) for task in sorted(tasks, key=task_rank, reverse=True)]


@router.post("/today/swap")
def swap_today(data: SwapInput = SwapInput(), user: User = Depends(get_current_user),
               session: Session = Depends(get_session)) -> dict[str, object]:
    settings_row, day_key, plan = _today_context(session, user)
    assignments = _assignments(session, user, plan) if plan else []
    current = next((item for item in assignments if item[0].id == data.task_id), None) if data.task_id else None
    if current is None:
        now_task, _, _, _, _ = _current_now(session, user)
        current = next((item for item in assignments if now_task and item[0].id == now_task.id), None)
    if current is None:
        raise HTTPException(status_code=409, detail="There is no Today task to swap")
    if len(plan.swapped_task_ids) >= 2:
        return {"swapped": False, "limit_reached": True, "rest_available": True,
                "message": "Let's stay with this one, or rest.", "day_key": day_key}
    old_task, was_anchor, position = current
    energy = plan.energy_level or settings_row.energy_today
    if energy is None:
        return {"swapped": False, "limit_reached": False, "rest_available": True,
                "message": "Choose your energy to find another task, or rest.", "day_key": day_key}
    excluded = {uuid.UUID(value) for value in plan.swapped_task_ids if _is_uuid(value)}
    excluded.add(old_task.id)
    candidates = session.scalars(select(Task).where(Task.owner_id == user.id,
        Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED]),
        Task.focus_state == FocusState.LATER, Task.energy_level == energy)).all()
    candidates = sorted((task for task in candidates if task.id not in excluded), key=task_rank, reverse=True)
    if not candidates:
        return {"swapped": False, "limit_reached": False, "rest_available": True,
                "message": "No matching task is waiting in Later. Rest is available.", "day_key": day_key}
    replacement = candidates[0]
    old_task.skip_count_today = old_task.skip_count_today + 1 if old_task.skip_day_key == day_key else 1
    old_task.skip_day_key = day_key
    plan.swapped_task_ids = [*plan.swapped_task_ids, str(old_task.id)]
    old_task.is_anchor, old_task.today_position, old_task.today_day_key = False, None, None
    set_focus_state(old_task, FocusState.LATER)
    set_focus_state(replacement, FocusState.TODAY)
    replacement.is_anchor, replacement.today_position, replacement.today_day_key = was_anchor, position, day_key
    assignment = session.scalar(select(DailyPlanTask).where(DailyPlanTask.user_id == user.id,
        DailyPlanTask.plan_id == plan.id, DailyPlanTask.task_id == old_task.id))
    if assignment is None:
        raise HTTPException(status_code=409, detail="Today's plan changed; refresh and try again")
    assignment.task_id = replacement.id
    assignment.is_anchor = was_anchor
    response = {"swapped": True, "limit_reached": False, "task": _task_view(replacement), "day_key": day_key}
    session.commit()
    return response


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


@router.get("/settings")
def get_settings(user: User = Depends(get_current_user), session: Session = Depends(get_session),
                 x_timezone: str | None = Header(default=None)) -> dict[str, object]:
    row = session.scalar(select(UserSettings).where(UserSettings.user_id == user.id))
    if row is None:
        timezone_name = "UTC"
        if x_timezone:
            try:
                ZoneInfo(x_timezone)
                timezone_name = x_timezone
            except (ValueError, ZoneInfoNotFoundError):
                pass
        row = UserSettings(user_id=user.id, timezone=timezone_name)
        session.add(row)
        session.flush()
    now = datetime.now(timezone.utc)
    day_key = _day(now, row.timezone)
    if row.day_key != day_key:
        row.day_key, row.energy_today = day_key, None
    session.commit()
    return _settings_view(row)


@router.put("/settings")
def update_settings(data: SettingsUpdate, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    row = _settings_row(session, user.id)
    changes = data.model_dump(exclude_unset=True)
    timezone_name = changes.get("timezone", row.timezone)
    if not isinstance(timezone_name, str):
        timezone_name = row.timezone
    try:
        ZoneInfo(timezone_name)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise HTTPException(status_code=422, detail="Timezone must be a valid IANA timezone") from exc
    if timezone_name != row.timezone:
        row.day_key, row.energy_today = None, None
    for key, value in changes.items():
        setattr(row, key, value)
    row.day_key = _day(datetime.now(timezone.utc), row.timezone)
    session.commit()
    return _settings_view(row)


@router.get("/drift")
def list_drift_events(user: User = Depends(get_current_user), limit: int = Query(default=100, ge=1, le=500),
                      session: Session = Depends(get_session)) -> list[dict[str, object]]:
    rows = session.scalars(select(DriftEvent).where(DriftEvent.user_id == user.id).order_by(DriftEvent.created_at.desc()).limit(limit)).all()
    return [{"id": row.id, "task_id": row.task_id, "focus_session_id": row.focus_session_id,
             "day_key": row.day_key, "trigger_type": row.trigger_type.value, "note": row.note,
             "created_at": row.created_at} for row in rows]


@router.post("/drift", status_code=status.HTTP_201_CREATED)
def create_drift_event(data: DriftCreate, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    settings_row = _settings_row(session, user.id)
    if data.task_id is not None and session.scalar(select(Task.id).where(Task.id == data.task_id, Task.owner_id == user.id)) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    focus = None
    if data.focus_session_id is not None:
        focus = session.scalar(select(FocusSession).where(FocusSession.id == data.focus_session_id, FocusSession.user_id == user.id))
        if focus is None:
            raise HTTPException(status_code=404, detail="Focus session not found")
    now = datetime.now(timezone.utc)
    row = DriftEvent(user_id=user.id, task_id=data.task_id or (focus.task_id if focus else None),
                     focus_session_id=data.focus_session_id, day_key=_day(now, settings_row.timezone),
                     trigger_type=data.trigger_type, note=data.note)
    session.add(row)
    session.commit()
    session.refresh(row)
    return {"id": row.id, "task_id": row.task_id, "focus_session_id": row.focus_session_id,
            "day_key": row.day_key, "trigger_type": row.trigger_type.value, "note": row.note, "created_at": row.created_at}


@router.get("/daily-closes")
def list_daily_closes(user: User = Depends(get_current_user), limit: int = Query(default=100, ge=1, le=500),
                      session: Session = Depends(get_session)) -> list[dict[str, object]]:
    rows = session.scalars(select(DailyClose).where(DailyClose.user_id == user.id).order_by(DailyClose.day_key.desc()).limit(limit)).all()
    return [{"id": row.id, "day_key": row.day_key, "done_list": row.done_list,
             "drift_summary": row.drift_summary, "tomorrow_task_id": row.tomorrow_task_id,
             "reflection": row.reflection, "created_at": row.created_at} for row in rows]


@router.put("/daily-closes/today")
def save_daily_close(data: DailyCloseCreate, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    settings_row = _settings_row(session, user.id)
    day_key = _day(datetime.now(timezone.utc), settings_row.timezone)
    if data.tomorrow_task_id is not None and session.scalar(select(Task.id).where(Task.id == data.tomorrow_task_id, Task.owner_id == user.id)) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    row = session.scalar(select(DailyClose).where(DailyClose.user_id == user.id, DailyClose.day_key == day_key))
    if row is None:
        row = DailyClose(user_id=user.id, day_key=day_key)
        session.add(row)
    row.done_list, row.drift_summary = data.done_list, data.drift_summary
    row.tomorrow_task_id, row.reflection = data.tomorrow_task_id, data.reflection
    for trigger in data.drift_triggers:
        session.add(DriftEvent(user_id=user.id, day_key=day_key, trigger_type=trigger))
    session.commit()
    session.refresh(row)
    return {"id": row.id, "day_key": row.day_key, "done_list": row.done_list,
            "drift_summary": row.drift_summary, "tomorrow_task_id": row.tomorrow_task_id,
            "reflection": row.reflection, "created_at": row.created_at}


@router.get("/close/today")
def get_close_today(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    settings_row, day_key, _ = _today_context(session, user)
    completed = session.scalars(select(Task).where(Task.owner_id == user.id, Task.status == TaskStatus.DONE,
        Task.completed_at.is_not(None))).all()
    done_list = [{"id": str(task.id), "title": task.title, "completed_at": task.completed_at.isoformat()}
                 for task in completed if local_day_key(task.completed_at, settings_row.timezone) == day_key]
    row = session.scalar(select(DailyClose).where(DailyClose.user_id == user.id, DailyClose.day_key == day_key))
    drift = session.scalars(select(DriftEvent).where(DriftEvent.user_id == user.id,
        DriftEvent.day_key == day_key).order_by(DriftEvent.created_at)).all()
    response = {"day_key": day_key, "done_list": row.done_list if row else done_list,
                "drift_triggers": [item.trigger_type.value for item in drift],
                "drift_summary": row.drift_summary if row else None,
                "tomorrow_task_id": row.tomorrow_task_id if row else None,
                "reflection": row.reflection if row else None}
    session.commit()
    return response


@router.get("/privacy/export")
def export_focus_data(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    drifts = session.scalars(select(DriftEvent).where(DriftEvent.user_id == user.id).order_by(DriftEvent.created_at)).all()
    closes = session.scalars(select(DailyClose).where(DailyClose.user_id == user.id).order_by(DailyClose.day_key)).all()
    return {"drift_events": [{"id": str(row.id), "task_id": str(row.task_id) if row.task_id else None,
             "focus_session_id": str(row.focus_session_id) if row.focus_session_id else None, "day_key": row.day_key,
             "trigger_type": row.trigger_type.value, "note": row.note, "created_at": row.created_at.isoformat()} for row in drifts],
            "daily_closes": [{"id": str(row.id), "day_key": row.day_key, "done_list": row.done_list,
             "drift_summary": row.drift_summary, "tomorrow_task_id": str(row.tomorrow_task_id) if row.tomorrow_task_id else None,
             "reflection": row.reflection, "created_at": row.created_at.isoformat()} for row in closes]}


@router.delete("/privacy/data", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None)
def delete_focus_data(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> Response:
    session.execute(delete(DriftEvent).where(DriftEvent.user_id == user.id))
    session.execute(delete(DailyClose).where(DailyClose.user_id == user.id))
    session.execute(delete(DailyPlanTask).where(DailyPlanTask.user_id == user.id))
    session.execute(delete(DailyPlan).where(DailyPlan.user_id == user.id))
    session.execute(delete(UserSettings).where(UserSettings.user_id == user.id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
