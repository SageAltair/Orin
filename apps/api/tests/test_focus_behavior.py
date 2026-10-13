from datetime import datetime, timezone
import uuid

from orin_api.focus_behavior import is_quiet_time, missed_days_since, prompt_form, rolling_completed_days
from orin_api.focus_domain import keep_task_in_review, release_task, shrink_task_step
from orin_api.models import FocusState, Task, TaskStatus


def test_rolling_week_counts_done_days_and_treats_rest_day_as_neutral() -> None:
    assert rolling_completed_days({"2026-10-14", "2026-10-12"}, "2026-10-15", rest_day=6) == 3
    assert rolling_completed_days(set(), "2026-10-15", rest_day=None) == 0


def test_reentry_absence_excludes_weekly_rest_day() -> None:
    assert missed_days_since("2026-10-10", "2026-10-14", rest_day=6) == 2
    assert missed_days_since("2026-10-10", "2026-10-14", rest_day=0) == 2


def test_quiet_hours_cover_daytime_and_windows_crossing_midnight() -> None:
    daytime = {"start": "09:00", "end": "17:00"}
    assert is_quiet_time(datetime(2026, 10, 10, 12, tzinfo=timezone.utc), daytime)
    assert not is_quiet_time(datetime(2026, 10, 10, 18, tzinfo=timezone.utc), daytime)
    overnight = {"start": "22:00", "end": "07:00"}
    assert is_quiet_time(datetime(2026, 10, 10, 23, tzinfo=timezone.utc), overnight)
    assert is_quiet_time(datetime(2026, 10, 10, 6, 59, tzinfo=timezone.utc), overnight)
    assert not is_quiet_time(datetime(2026, 10, 10, 8, tzinfo=timezone.utc), overnight)


def test_routine_prompt_escalation_stops_after_two_reminders() -> None:
    assert [prompt_form(count) for count in range(4)] == ["gentle", "softer", None, None]


def test_decay_keep_shrink_and_release_use_consistent_task_transitions() -> None:
    now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    task = Task(owner_id=uuid.uuid4(), title="Prepare draft", status=TaskStatus.TODO,
                focus_state=FocusState.LATER, first_step="Open document")
    task.decay_review_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    keep_task_in_review(task, now=now)
    assert task.last_touched_at == now
    assert task.decay_review_at == datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
    shrink_task_step(task, "Write one sentence", now=now)
    assert task.first_step == "Write one sentence"
    assert task.decay_review_at == datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
    release_task(task, now=now)
    assert task.status == TaskStatus.CANCELLED
    assert task.focus_state == FocusState.RELEASED
    assert task.released_at == now
