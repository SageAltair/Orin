"""Deterministic relevance rules, deduplication and bounded opt-in escalation."""

import re
import uuid
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from orin_api.models import (
    Notification,
    NotificationPreferences,
    Task,
    TaskStatus,
    Project,
    ProjectStatus,
    Opportunity,
    Risk,
    Approval,
    ApprovalStatus,
    WorkerJob,
    WorkerJobStatus,
    KnowledgeExtractionJob,
    FocusSession,
    Routine,
    RoutineCheckin,
    CalendarEvent,
    UserSettings,
    TaskSchedule,
    Milestone,
    KnowledgeDocument,
)

CATEGORIES = [
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


def utc(value):
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def policy(session, user_id):
    row = session.get(NotificationPreferences, user_id)
    if row is None:
        try:
            with session.begin_nested():
                focus_settings = session.get(UserSettings, user_id)
                row = NotificationPreferences(
                    user_id=user_id,
                    timezone=focus_settings.timezone if focus_settings else "UTC",
                )
                session.add(row)
                session.flush()
        except IntegrityError:
            row = session.get(NotificationPreferences, user_id)
    return row


def safe_zone(value: str | None) -> ZoneInfo | None:
    """Legacy invalid timezone values must not abort every user's reminder tick."""
    try:
        return ZoneInfo(value)
    except (KeyError, TypeError, ValueError):
        return None


def category_enabled(prefs, category: str) -> bool:
    """Fail closed for corrupt legacy JSON category preferences."""
    return bool(prefs.enabled and isinstance(prefs.categories, list) and category in prefs.categories)


def attention_allowed(session, prefs, now):
    if not prefs.enabled:
        return False
    zone = safe_zone(prefs.timezone)
    if zone is None:
        return False  # Never bypass quiet hours with an invented UTC fallback.
    clock = now.astimezone(zone).strftime("%H:%M")
    if prefs.quiet_enabled:
        start, end = prefs.quiet_start, prefs.quiet_end
        # Invalid legacy wall clocks must never silently bypass quiet hours.
        if not all(
            isinstance(value, str)
            and re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value)
            for value in (start, end)
        ):
            return False
        if (
            (start < end and start <= clock < end)
            or (start > end and (clock >= start or clock < end))
            or start == end
        ):
            return False
    if prefs.respect_focus:
        active = session.scalars(
            select(FocusSession).where(
                FocusSession.user_id == prefs.user_id, FocusSession.status == "active"
            )
        ).all()
        if any(
            utc(row.started_at)
            <= now
            < utc(row.started_at) + timedelta(minutes=row.duration_minutes)
            for row in active
        ):
            return False
    return True


def emit(
    session,
    *,
    user_id,
    key,
    title,
    message,
    due,
    category,
    source_id=None,
    event_id=None,
):
    prefs = policy(session, user_id)
    if not category_enabled(prefs, category):
        return
    if session.scalar(select(Notification.id).where(Notification.delivery_key == key)):
        return
    try:
        with session.begin_nested():
            session.add(
                Notification(
                    user_id=user_id,
                    delivery_key=key,
                    title=title[:240],
                    message=message[:500],
                    due_at=due,
                    category=category,
                    source_id=source_id,
                    event_id=event_id,
                )
            )
            session.flush()
    except IntegrityError:
        pass


def _source_uuid_in_delivery_key(key: str) -> uuid.UUID | None:
    """Treat corrupt/legacy reminder keys as stale, not a fatal worker error."""
    try:
        return uuid.UUID(key.split(":", 2)[1])
    except (ValueError, IndexError):
        return None


def relevant(session, row):
    model = {
        "tasks": Task,
        "projects": Project,
        "opportunities": Opportunity,
        "risks": Risk,
        "approvals": Approval,
        "jobs": WorkerJob,
        "writing": KnowledgeExtractionJob,
        "routines": Routine,
        "calendar": CalendarEvent,
    }.get(row.category)
    if row.category == "writing" and row.delivery_key.startswith("writing-review:"):
        model = KnowledgeDocument
    if (
        row.source_id is None
        and row.category == "routines"
        and row.delivery_key.startswith("routine:")
    ):
        try:
            row.source_id = uuid.UUID(row.delivery_key.split(":")[1])
        except (ValueError, IndexError):
            return False
    source_id = row.source_id or row.event_id
    if not model or not source_id:
        return True  # Older reminders retain their history.
    source = session.get(model, source_id)
    if source is None:
        return False
    owner = getattr(
        source,
        "user_id",
        getattr(source, "owner_id", getattr(source, "requested_by_id", None)),
    )
    if owner != row.user_id:
        return False
    if row.category == "tasks":
        if source.status in {TaskStatus.DONE, TaskStatus.CANCELLED}:
            return False
        if row.delivery_key.startswith("task-block:"):
            block_id = _source_uuid_in_delivery_key(row.delivery_key)
            if block_id is None:
                return False
            block = session.get(TaskSchedule, block_id)
            return bool(
                block
                and block.task_id == source.id
                and utc(block.start_at) == utc(row.due_at)
            )
        date = (
            source.decay_review_at
            if row.delivery_key.startswith("task-review:")
            else source.due_at
        )
        return date is not None and utc(date) == utc(row.due_at)
    if row.category == "projects":
        if source.status != ProjectStatus.ACTIVE:
            return False
        if row.delivery_key.startswith("milestone:"):
            milestone_id = _source_uuid_in_delivery_key(row.delivery_key)
            if milestone_id is None:
                return False
            milestone = session.get(Milestone, milestone_id)
            return bool(
                milestone
                and milestone.project_id == source.id
                and milestone.status == "pending"
                and milestone.target_date
                and milestone.target_date.isoformat() in row.delivery_key
            )
        return (
            source.target_date is not None
            and source.target_date.isoformat() in row.delivery_key
        )
    if row.category == "opportunities":
        return source.stage not in {"won", "closed"} and any(
            d and d.isoformat() in row.delivery_key
            for d in (source.review_on, source.deadline)
        )
    if row.category == "risks":
        return (
            source.status != "resolved"
            and source.review_on is not None
            and source.review_on.isoformat() in row.delivery_key
        )
    if row.category == "approvals":
        return source.status == ApprovalStatus.PENDING
    if row.category == "jobs":
        return source.status in {WorkerJobStatus.FAILED, WorkerJobStatus.EXPIRED}
    if row.category == "writing":
        if row.delivery_key.startswith("writing-review:"):
            return (
                not source.archived
                and source.review_at is not None
                and utc(source.review_at) == utc(row.due_at)
            )
        return source.status == "failed"
    if row.category == "routines":
        if source.paused or source.reminder_minutes is None:
            return False
        zone = safe_zone(source.timezone)
        if zone is None:
            return False
        day = utc(row.due_at).astimezone(zone).date()
        # Reminder before midnight can refer to the following day.
        from orin_api.planning_domain import occurrence

        for local_day in (day, day + timedelta(days=1)):
            try:
                instant = occurrence(source, local_day)
            except (ValueError, TypeError, KeyError):
                return False  # Invalid legacy clock; never interrupt other users.
            if instant and instant.isoformat() in row.delivery_key:
                return not session.scalar(
                    select(RoutineCheckin.id).where(
                        RoutineCheckin.routine_id == source.id,
                        RoutineCheckin.day == local_day,
                    )
                )
        return False
    if row.category == "calendar":
        if source.reminder_minutes is None:
            return False
        if source.is_all_day:
            zone = safe_zone(source.timezone)
            if zone is None:
                return False
            start = datetime.combine(
                source.start_date, time(9), zone
            ).astimezone(timezone.utc)
        else:
            start = utc(source.start_at)
        return start - timedelta(minutes=source.reminder_minutes) == utc(row.due_at)
    return True


def notification_tick(session, now):
    # One actionable reminder per source/schedule. Old backlogs are bounded to seven days.
    for task in session.scalars(
        select(Task).where(
            Task.due_at.between(now - timedelta(days=7), now + timedelta(minutes=30)),
            Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
        )
    ):
        due = utc(task.due_at)
        emit(
            session,
            user_id=task.owner_id,
            key=f"task:{task.id}:{due.isoformat()}",
            title=task.title,
            message="A task deadline is approaching or has passed. Choose a small step or revise the plan.",
            due=due,
            category="tasks",
            source_id=task.id,
        )
    for block in session.scalars(
        select(TaskSchedule).where(
            TaskSchedule.start_at.between(
                now - timedelta(hours=1), now + timedelta(minutes=10)
            )
        )
    ):
        task = session.get(Task, block.task_id)
        if task and task.status not in {TaskStatus.DONE, TaskStatus.CANCELLED}:
            emit(
                session,
                user_id=task.owner_id,
                key=f"task-block:{block.id}:{utc(block.start_at).isoformat()}",
                title=task.title,
                message="Your scheduled work block is ready. Start with its first small step.",
                due=utc(block.start_at),
                category="tasks",
                source_id=task.id,
            )
    for task in session.scalars(
        select(Task).where(Task.decay_review_at.between(now - timedelta(days=7), now))
    ):
        if task.status not in {TaskStatus.DONE, TaskStatus.CANCELLED}:
            emit(
                session,
                user_id=task.owner_id,
                key=f"task-review:{task.id}:{utc(task.decay_review_at).isoformat()}",
                title=task.title,
                message="This task is ready for review. Keep it, make it smaller, or release it.",
                due=utc(task.decay_review_at),
                category="tasks",
                source_id=task.id,
            )
    for document in session.scalars(
        select(KnowledgeDocument).where(
            KnowledgeDocument.review_at.between(now - timedelta(days=7), now)
        )
    ):
        if not document.archived:
            emit(
                session,
                user_id=document.user_id,
                key=f"writing-review:{document.id}:{utc(document.review_at).isoformat()}",
                title=document.title,
                message="Your saved Writing review date has arrived.",
                due=utc(document.review_at),
                category="writing",
                source_id=document.id,
            )
    for milestone in session.scalars(
        select(Milestone).where(
            Milestone.status == "pending", Milestone.target_date.is_not(None)
        )
    ):
        project = session.get(Project, milestone.project_id)
        if project and project.status == ProjectStatus.ACTIVE:
            prefs = policy(session, project.owner_id)
            zone = safe_zone(prefs.timezone)
            if zone is None:
                continue
            day = now.astimezone(zone).date()
            if day - timedelta(days=7) <= milestone.target_date <= day:
                due = datetime.combine(
                    milestone.target_date, datetime.min.time(), zone
                ).astimezone(timezone.utc)
                emit(
                    session,
                    user_id=project.owner_id,
                    key=f"milestone:{milestone.id}:{milestone.target_date}",
                    title=milestone.title,
                    message="A project milestone is ready for review.",
                    due=due,
                    category="projects",
                    source_id=project.id,
                )
    for model, category, title_field, date_fields in (
        (Project, "projects", "name", ("target_date",)),
        (Opportunity, "opportunities", "title", ("review_on", "deadline")),
        (Risk, "risks", "title", ("review_on",)),
    ):
        for source in session.scalars(select(model)):
            owner = getattr(source, "user_id", getattr(source, "owner_id", None))
            prefs = policy(session, owner)
            zone = safe_zone(prefs.timezone)
            if zone is None:
                continue
            local_day = now.astimezone(zone).date()
            for field in date_fields:
                day = getattr(source, field)
                if day and local_day - timedelta(days=7) <= day <= local_day:
                    due = datetime.combine(
                        day, datetime.min.time(), zone
                    ).astimezone(timezone.utc)
                    key = f"{category}:{source.id}:{field}:{day}"
                    # The source state is checked before delivery and during later escalation.
                    probe = Notification(
                        user_id=owner,
                        category=category,
                        source_id=source.id,
                        delivery_key=key,
                        due_at=due,
                    )
                    if relevant(session, probe):
                        emit(
                            session,
                            user_id=owner,
                            key=key,
                            title=getattr(source, title_field),
                            message=f"Review this {dict(projects='project',opportunities='opportunity',risks='risk')[category]} and choose its next step.",
                            due=due,
                            category=category,
                            source_id=source.id,
                        )
    for model, category in (
        (Approval, "approvals"),
        (WorkerJob, "jobs"),
        (KnowledgeExtractionJob, "writing"),
    ):
        for source in session.scalars(
            select(model).where(model.created_at >= now - timedelta(days=7))
        ):
            owner = getattr(source, "user_id", getattr(source, "requested_by_id", None))
            key = f"{category}:{source.id}"
            probe = Notification(
                user_id=owner,
                category=category,
                source_id=source.id,
                delivery_key=key,
                due_at=now,
            )
            if relevant(session, probe):
                emit(
                    session,
                    user_id=owner,
                    key=key,
                    title={
                        "approvals": "Approval needs your decision",
                        "jobs": "Worker job needs attention",
                        "writing": "Writing analysis needs attention",
                    }[category],
                    message="Open the related workspace to review the result and decide what to do next.",
                    due=now,
                    category=category,
                    source_id=source.id,
                )
    rows = session.scalars(
        select(Notification)
        .where(Notification.read_at.is_(None))
        .order_by(Notification.user_id, Notification.due_at)
        .with_for_update(skip_locked=True)
    ).all()
    for row in rows:
        prefs = policy(session, row.user_id)
        if (
            row.category in {"calendar", "routines"}
            and utc(row.due_at) + timedelta(hours=2) < now
        ) or not relevant(session, row):
            row.read_at = now
            continue
        if not category_enabled(prefs, row.category):
            continue
        if row.snoozed_until and utc(row.snoozed_until) > now:
            continue
        if not attention_allowed(session, prefs, now):
            continue
        if row.attention_at is None:
            row.attention_at = now
            continue
        if (
            not prefs.persistent
            or row.repeats >= prefs.max_repeats
            or utc(row.attention_at) + timedelta(minutes=prefs.repeat_minutes) > now
        ):
            continue
        # Shared preferences lock serializes the daily per-user repeat budget across API instances.
        session.refresh(prefs, with_for_update=True)
        if (
            not category_enabled(prefs, row.category)
            or not prefs.persistent
            or row.repeats >= prefs.max_repeats
        ):
            continue
        zone = safe_zone(prefs.timezone)
        if zone is None:
            continue
        local_day = now.astimezone(zone).date()
        if prefs.repeat_day != local_day:
            prefs.repeat_day = local_day
            prefs.repeats_today = 0
        if prefs.repeats_today >= 8:
            continue
        row.repeats += 1
        row.revision += 1
        row.attention_at = now
        prefs.repeats_today += 1
