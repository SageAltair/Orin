import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from orin_api.auth import get_current_user
from orin_api.config import Settings, get_settings
from orin_api.database import Base, get_session
from orin_api.main import app
from orin_api.models import (
    Activity,
    ActivityType,
    CreativeDocumentCard,
    CreativeOutlineItem,
    IdeaDocumentLink,
    IdeaInbox,
    User,
)


@pytest.fixture
def sessions() -> Generator[tuple[sessionmaker, uuid.UUID], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        user = User(
            email="studio@example.test",
            password_hash="test-hash",
            display_name="Studio",
        )
        session.add(user)
        session.flush()
        owner_id = user.id
    try:
        yield factory, owner_id
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(
    sessions: tuple[sessionmaker, uuid.UUID],
) -> Generator[TestClient, None, None]:
    factory, owner_id = sessions

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    def current_user() -> User:
        with factory() as session:
            user = session.get(User, owner_id)
            assert user is not None
            return user

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def _project(client: TestClient, name: str = "The Small Voice") -> dict[str, object]:
    response = client.post(
        "/api/v1/projects", json={"name": name, "objective": "Help people grow"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _note(client: TestClient, title: str = "Opening scene") -> dict[str, object]:
    response = client.post(
        "/api/v1/knowledge/documents",
        json={"title": title, "content": "A first line.", "document_type": "draft"},
    )
    assert response.status_code == 201, response.text
    return response.json()


from datetime import datetime, timedelta, timezone
from orin_api.notifications import notification_tick, policy, attention_allowed
from orin_api.models import Notification, Task, TaskStatus, FocusSession


def tick(factory, now):
    with factory.begin() as session:
        notification_tick(session, now)


def task(factory, owner, now, title="One next action"):
    with factory.begin() as session:
        row = Task(owner_id=owner, title=title, due_at=now)
        session.add(row)
        session.flush()
        return row.id


def test_due_task_is_deduplicated_and_completion_stops_followup(sessions):
    factory, owner = sessions
    now = datetime.now(timezone.utc)
    item = task(factory, owner, now)
    tick(factory, now)
    tick(factory, now + timedelta(seconds=15))
    with factory.begin() as session:
        rows = session.scalars(select(Notification)).all()
        assert len(rows) == 1
        assert rows[0].category == "tasks" and rows[0].repeats == 0
        session.get(Task, item).status = TaskStatus.DONE
    tick(factory, now + timedelta(minutes=30))
    with factory() as session:
        assert session.scalar(select(Notification)).read_at is not None


def test_corrupt_task_block_and_milestone_keys_do_not_abort_notification_tick(client, sessions):
    factory, owner = sessions
    now = datetime.now(timezone.utc)
    task_id = task(factory, owner, now)
    project_id = uuid.UUID(_project(client)["id"])
    invalid = [
        ("tasks", task_id, "task-block:not-a-uuid:2026-10-31T12:00:00Z"),
        ("tasks", task_id, "task-block:"),
        ("projects", project_id, "milestone:not-a-uuid:2026-10-31"),
        ("projects", project_id, "milestone:"),
    ]
    with factory.begin() as session:
        session.add_all([
            Notification(
                user_id=owner, category=category, source_id=source_id,
                delivery_key=key, title="Old reminder", message="Stale key",
                due_at=now,
            )
            for category, source_id, key in invalid
        ])

    # One corrupt persisted row must not stop valid tasks from receiving
    # reminders or repeatedly crash the worker on every scheduled tick.
    tick(factory, now)
    with factory() as session:
        rows = session.scalars(select(Notification)).all()
        by_key = {row.delivery_key: row for row in rows}
        for _, _, key in invalid:
            assert by_key[key].read_at is not None
        valid = [
            row for row in rows
            if row.category == "tasks" and row.delivery_key.startswith("task:")
        ]
        assert len(valid) == 1
        assert valid[0].read_at is None


def test_task_due_time_creates_in_app_reminder_and_rescheduling_invalidates_old_one(client, sessions):
    factory, _ = sessions
    now = datetime.now(timezone.utc)
    first_due = now + timedelta(minutes=25)
    created = client.post(
        "/api/v1/tasks", json={"title": "Time-specific reminder", "due_at": first_due.isoformat()}
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]

    tick(factory, now)
    rows = client.get("/api/v1/notifications").json()
    assert len(rows) == 1 and rows[0]["attention_ready"]
    assert rows[0]["category"] == "tasks"
    assert datetime.fromisoformat(rows[0]["due_at"]) == first_due

    later_due = now + timedelta(hours=2)
    updated = client.patch(f"/api/v1/tasks/{task_id}", json={"due_at": later_due.isoformat()})
    assert updated.status_code == 200, updated.text
    rows = client.get("/api/v1/notifications").json()
    assert rows[0]["read_at"] is not None
    assert not rows[0]["attention_ready"]

    tick(factory, now + timedelta(hours=1, minutes=31))
    rows = client.get("/api/v1/notifications").json()
    assert len(rows) == 2
    assert any(datetime.fromisoformat(row["due_at"]) == later_due for row in rows)
    assert sum(row["read_at"] is None for row in rows) == 1

    completed = client.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
    assert completed.status_code == 200, completed.text
    assert all(row["read_at"] is not None for row in client.get("/api/v1/notifications").json())


def test_persistent_requires_opt_in_and_respects_repeat_limit(sessions):
    factory, owner = sessions
    now = datetime.now(timezone.utc)
    task(factory, owner, now)
    tick(factory, now)
    tick(factory, now + timedelta(minutes=6))
    with factory.begin() as session:
        assert session.scalar(select(Notification)).repeats == 0
        prefs = policy(session, owner)
        prefs.persistent = True
        prefs.repeat_minutes = 5
        prefs.max_repeats = 2
    for minutes in (7, 13, 20, 30):
        tick(factory, now + timedelta(minutes=minutes))
    with factory() as session:
        row = session.scalar(select(Notification))
        assert row.repeats == 2 and row.revision == 3


def test_daily_repeat_budget_is_shared(sessions):
    factory, owner = sessions
    # Fix the clock so a CI run near UTC midnight cannot cross the daily budget reset.
    now = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
    for i in range(10):
        task(factory, owner, now, title=f"Task {i}")
    with factory.begin() as session:
        policy(session, owner).persistent = True
    tick(factory, now)
    tick(factory, now + timedelta(minutes=16))
    tick(factory, now + timedelta(minutes=32))
    with factory() as session:
        assert sum(row.repeats for row in session.scalars(select(Notification))) == 8


def test_daily_repeat_budget_resets_at_user_local_midnight(sessions):
    factory, owner = sessions
    # Auckland is UTC+13 on this date: 10:34 UTC is 23:34 local.
    now = datetime(2026, 10, 13, 10, 34, tzinfo=timezone.utc)
    for i in range(10):
        task(factory, owner, now, title=f"Local midnight task {i}")
    with factory.begin() as session:
        prefs = policy(session, owner)
        prefs.persistent = True
        prefs.timezone = "Pacific/Auckland"
    tick(factory, now)
    tick(factory, now + timedelta(minutes=16))  # 23:50 local, first day's cap
    with factory() as session:
        assert sum(row.repeats for row in session.scalars(select(Notification))) == 8
        assert policy(session, owner).repeat_day.isoformat() == "2026-10-13"
    tick(factory, now + timedelta(minutes=32))  # 00:06 local, new day's cap
    with factory() as session:
        assert sum(row.repeats for row in session.scalars(select(Notification))) == 16
        prefs = policy(session, owner)
        assert prefs.repeat_day.isoformat() == "2026-10-14"
        assert prefs.repeats_today == 8


def test_quiet_hours_and_active_focus_defer_interruptions(sessions):
    factory, owner = sessions
    now = datetime(2026, 10, 13, 23, 0, tzinfo=timezone.utc)
    with factory.begin() as session:
        prefs = policy(session, owner)
        prefs.quiet_enabled = True
        assert not attention_allowed(session, prefs, now)
        assert not attention_allowed(session, prefs, now + timedelta(hours=7))
        assert attention_allowed(session, prefs, now + timedelta(hours=8))
        prefs.quiet_enabled = False
        session.add(
            FocusSession(
                user_id=owner,
                objective="Read",
                duration_minutes=25,
                started_at=now,
                status="active",
            )
        )
        session.flush()
        assert not attention_allowed(session, prefs, now + timedelta(minutes=10))
        assert attention_allowed(session, prefs, now + timedelta(minutes=30))


def test_snooze_acknowledgement_and_ownership(client, sessions):
    factory, owner = sessions
    now = datetime.now(timezone.utc)
    task(factory, owner, now)
    tick(factory, now)
    rows = client.get("/api/v1/notifications").json()
    assert rows[0]["attention_ready"]
    assert datetime.fromisoformat(
        rows[0]["due_at"].replace("Z", "+00:00")
    ).utcoffset() == timedelta(0)
    endpoint = f"/api/v1/notifications/{rows[0]['id']}/action"
    assert (
        client.post(endpoint, json={"action": "snooze", "minutes": 15}).status_code
        == 200
    )
    assert not client.get("/api/v1/notifications").json()[0]["attention_ready"]
    assert client.post(endpoint, json={"action": "acknowledge"}).status_code == 200
    assert client.get("/api/v1/notifications").json()[0]["read_at"]
    assert (
        client.post(
            f"/api/v1/notifications/{uuid.uuid4()}/action",
            json={"action": "acknowledge"},
        ).status_code
        == 404
    )


def test_preferences_validation_and_disable(client, sessions):
    prefs = client.get("/api/v1/notifications/preferences").json()
    assert not prefs["persistent"]
    for patch in (
        {"timezone": "bad/zone"},
        {"repeat_minutes": 0},
        {"quiet_start": "25:00"},
        {"categories": ["unknown"]},
    ):
        assert (
            client.put(
                "/api/v1/notifications/preferences", json={**prefs, **patch}
            ).status_code
            == 422
        )
    prefs["enabled"] = False
    assert (
        client.put("/api/v1/notifications/preferences", json=prefs).status_code == 200
    )
    factory, owner = sessions
    now = datetime.now(timezone.utc)
    task(factory, owner, now)
    tick(factory, now)
    assert client.get("/api/v1/notifications").json() == []


def test_reviews_cover_projects_opportunities_and_risks(client, sessions):
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    client.post(
        "/api/v1/projects", json={"name": "Ship a small release", "target_date": today}
    )
    opportunity = client.post(
        "/api/v1/opportunities", json={"title": "Collaboration", "review_on": today}
    ).json()
    risk = client.post(
        "/api/v1/risks", json={"title": "Capacity", "review_on": today}
    ).json()
    factory, owner = sessions
    tick(factory, now)
    assert {row["category"] for row in client.get("/api/v1/notifications").json()} == {
        "projects",
        "opportunities",
        "risks",
    }
    data = {k: v for k, v in risk.items() if k != "id"}
    data["status"] = "resolved"
    client.put(f"/api/v1/risks/{risk['id']}", json=data)
    tick(factory, now + timedelta(minutes=5))
    assert next(
        row
        for row in client.get("/api/v1/notifications").json()
        if row["category"] == "risks"
    )["read_at"]


def test_scheduled_work_milestones_and_writing_reviews(sessions):
    from orin_api.models import TaskSchedule, Milestone, Project, KnowledgeDocument

    factory, owner = sessions
    now = datetime.now(timezone.utc)
    item = task(factory, owner, now + timedelta(days=2))
    with factory.begin() as session:
        project = Project(owner_id=owner, name="A project")
        session.add(project)
        session.flush()
        session.add_all(
            [
                TaskSchedule(
                    user_id=owner,
                    task_id=item,
                    start_at=now,
                    end_at=now + timedelta(minutes=25),
                    estimated_minutes=25,
                ),
                Milestone(
                    project_id=project.id, title="First draft", target_date=now.date()
                ),
                KnowledgeDocument(
                    user_id=owner,
                    title="Review this idea",
                    review_at=now,
                    content="A thought",
                ),
            ]
        )
    tick(factory, now)
    with factory() as session:
        keys = [
            row.delivery_key.split(":")[0]
            for row in session.scalars(select(Notification))
        ]
        assert set(keys) == {"task-block", "milestone", "writing-review"}


def test_foreign_notification_cannot_be_read_or_snoozed(client, sessions):
    factory, owner = sessions
    with factory.begin() as session:
        other = User(
            email="notification-other@example.test",
            display_name="Other",
            password_hash="fake",
        )
        session.add(other)
        session.flush()
        row = Notification(
            user_id=other.id,
            title="Private reminder",
            message="Private",
            delivery_key="private:test",
            due_at=datetime.now(timezone.utc),
        )
        session.add(row)
        session.flush()
        item = row.id
    assert client.get("/api/v1/notifications").json() == []
    assert client.patch(f"/api/v1/notifications/{item}/read").status_code == 404
    assert (
        client.post(
            f"/api/v1/notifications/{item}/action",
            json={"action": "snooze", "minutes": 15},
        ).status_code
        == 404
    )


def test_saved_reminder_becomes_ready_immediately_when_quiet_hours_end(
    client, sessions
):
    factory, owner = sessions
    now = datetime.now(timezone.utc)
    item = task(factory, owner, now)
    with factory.begin() as session:
        prefs = policy(session, owner)
        prefs.quiet_enabled = True
        prefs.quiet_start = prefs.quiet_end = "00:00"
        session.add(
            Notification(
                user_id=owner,
                source_id=item,
                category="tasks",
                delivery_key="task:quiet-test",
                title="Ready after quiet",
                message="A next step",
                due_at=now,
            )
        )
    assert not client.get("/api/v1/notifications").json()[0]["attention_ready"]
    prefs = client.get("/api/v1/notifications/preferences").json()
    prefs["quiet_enabled"] = False
    assert (
        client.put("/api/v1/notifications/preferences", json=prefs).status_code == 200
    )
    assert client.get("/api/v1/notifications").json()[0]["attention_ready"]
