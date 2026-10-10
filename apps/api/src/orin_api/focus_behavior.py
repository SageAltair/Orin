"""Pure calendar and reminder rules for Focus behavior."""
from __future__ import annotations

from datetime import date, datetime


def rolling_completed_days(completed_day_keys: set[str], day_key: str, rest_day: int | None) -> int:
    end = date.fromisoformat(day_key)
    return sum(
        day.isoformat() in completed_day_keys or (rest_day is not None and day.weekday() == rest_day)
        for offset in range(7)
        for day in [date.fromordinal(end.toordinal() - offset)]
    )


def missed_days_since(last_seen_day_key: str, today_key: str, rest_day: int | None) -> int:
    start, end = date.fromisoformat(last_seen_day_key), date.fromisoformat(today_key)
    missed = 0
    for ordinal in range(start.toordinal() + 1, end.toordinal()):
        day = date.fromordinal(ordinal)
        if rest_day is not None and day.weekday() == rest_day:
            continue
        missed += 1
    return missed


def is_quiet_time(local_time: datetime, quiet_hours: dict[str, str] | None) -> bool:
    if not quiet_hours:
        return False
    start = datetime.strptime(quiet_hours["start"], "%H:%M").time()
    end = datetime.strptime(quiet_hours["end"], "%H:%M").time()
    now = local_time.timetz().replace(tzinfo=None)
    if start == end:
        return True
    return start <= now < end if start < end else now >= start or now < end


def prompt_form(count: int) -> str | None:
    """Limit in-app prompts per task/day and use a softer second prompt."""
    if count <= 0:
        return "gentle"
    if count == 1:
        return "softer"
    if count == 2:
        return "visual_on_open"
    return None
