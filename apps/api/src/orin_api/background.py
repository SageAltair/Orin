"""Recover durable jobs and deliver calendar reminders independently of open pages."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from orin_api.config import Settings
from orin_api.database import SessionLocal
from orin_api.knowledge_extraction import process_extraction_job
from orin_api.services import add_activity
from orin_api.models import ActivityType, CalendarEvent, KnowledgeExtractionJob, Notification, WorkerJob, WorkerJobStatus

logger = logging.getLogger(__name__)


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def maintenance_tick(settings: Settings, *, now: datetime | None = None) -> None:
    current = now or datetime.now(timezone.utc)
    with SessionLocal() as session:
        stale = session.scalars(select(KnowledgeExtractionJob).where(
            KnowledgeExtractionJob.status.in_(["processing", "retrying"]),
            KnowledgeExtractionJob.updated_at < current - timedelta(minutes=10),
        ).with_for_update(skip_locked=True)).all()
        for job in stale:
            job.status, job.error = "queued", "Recovering interrupted analysis."
        expired = session.scalars(select(WorkerJob).where(
            WorkerJob.status.in_([WorkerJobStatus.QUEUED, WorkerJobStatus.STARTING, WorkerJobStatus.RUNNING]),
            WorkerJob.expires_at <= current,
        ).with_for_update(skip_locked=True)).all()
        for job in expired:
            job.status, job.finished_at = WorkerJobStatus.EXPIRED, current
            job.failure = "The job expired before a confirmed result was received."
            add_activity(session, user_id=job.user_id, actor_user_id=None,
                activity_type=ActivityType.WORKER_JOB_TIMED_OUT, summary="Worker job timed out",
                worker_job_id=job.id, approval_id=job.approval_id, result_status="expired", severity="warning",
                source="worker", idempotency_key=f"worker.terminal:{job.id}")
        events = session.scalars(select(CalendarEvent).where(CalendarEvent.reminder_minutes.is_not(None))).all()
        for event in events:
            start = (datetime.combine(event.start_date, time(9), ZoneInfo(event.timezone)).astimezone(timezone.utc)
                     if event.is_all_day else utc(event.start_at))
            due = start - timedelta(minutes=event.reminder_minutes)
            # Recover missed reminders during an outage, without surfacing old events indefinitely.
            if not due <= current < start + timedelta(hours=1):
                continue
            key = f"calendar:{event.id}:{start.isoformat()}:{event.reminder_minutes}"
            if session.scalar(select(Notification.id).where(Notification.delivery_key == key)) is not None:
                continue
            try:
                with session.begin_nested():
                    session.add(Notification(user_id=event.user_id, event_id=event.id, delivery_key=key,
                        title=event.title, message="Your calendar event is coming up.", due_at=due))
                    session.flush()
            except IntegrityError:
                pass  # Another API instance delivered the same reminder.
        jobs = session.scalars(select(KnowledgeExtractionJob.id).where(
            KnowledgeExtractionJob.status == "queued"
        ).order_by(KnowledgeExtractionJob.created_at).limit(4)).all()
        session.commit()
    for job_id in jobs:
        process_extraction_job(job_id, settings)


def maintenance_loop(stopping: threading.Event, settings: Settings) -> None:
    while not stopping.is_set():
        try:
            maintenance_tick(settings)
        except Exception:
            logger.error("Background maintenance failed; retrying without exposing job contents.")
        stopping.wait(15)
