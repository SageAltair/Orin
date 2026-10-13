"""Bounded, timezone-aware routine recurrence; no background creation of calendar rows."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from orin_api.models import Routine


def occurrence(routine: Routine, day: date) -> datetime | None:
    if (
        day < routine.start_date
        or (routine.end_date and day > routine.end_date)
        or day.weekday() not in routine.weekdays
    ):
        return None
    local = datetime.combine(
        day, time.fromisoformat(routine.time_of_day), ZoneInfo(routine.timezone)
    )
    instant = local.astimezone(timezone.utc)
    # Skip a nonexistent spring-forward wall time; choose the first fold in autumn.
    if instant.astimezone(ZoneInfo(routine.timezone)).replace(
        tzinfo=None
    ) != local.replace(tzinfo=None):
        return None
    return instant


def dates(start: date, end: date):
    for offset in range((end - start).days + 1):
        yield start + timedelta(days=offset)
