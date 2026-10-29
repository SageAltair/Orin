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


def test_opportunity_next_action_creates_one_owned_task(client, sessions):
    created = client.post(
        "/api/v1/opportunities",
        json={"title": "A collaboration", "next_action": "Read the brief"},
    )
    assert created.status_code == 201
    endpoint = f"/api/v1/opportunities/{created.json()['id']}/next-task"
    task_id = client.post(endpoint).json()["task_id"]
    assert client.post(endpoint).json()["task_id"] == task_id
    assert client.get("/api/v1/tasks").json()[0]["title"] == "Read the brief"


def test_private_references_and_rows(client, sessions):
    from orin_api.models import Opportunity, Risk, Routine, Project

    factory, owner = sessions
    with factory.begin() as session:
        other = User(
            email="other-planning@test.example",
            password_hash="test",
            display_name="Other",
        )
        session.add(other)
        session.flush()
        project = Project(owner_id=other.id, name="Private")
        opportunity = Opportunity(user_id=other.id, title="Private opening")
        routine = Routine(
            user_id=other.id,
            title="Private routine",
            start_date=__import__("datetime").date.today(),
        )
        session.add_all([project, opportunity, routine])
        session.flush()
        project_id, opportunity_id, routine_id = project.id, opportunity.id, routine.id
    assert client.get("/api/v1/opportunities").json() == []
    assert (
        client.post(
            "/api/v1/opportunities",
            json={"title": "Bad reference", "project_id": str(project_id)},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/risks",
            json={"title": "Bad reference", "opportunity_id": str(opportunity_id)},
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/opportunities/{opportunity_id}").status_code == 404
    assert client.delete(f"/api/v1/calendar/routines/{routine_id}").status_code == 404


def test_risk_update_and_resolution(client):
    risk = client.post(
        "/api/v1/risks",
        json={"title": "Deadline conflict", "impact": 5, "likelihood": 4},
    ).json()
    risk.pop("id")
    risk["status"] = "resolved"
    risk["mitigation"] = "Ask about the timeline before committing"
    rows = client.get("/api/v1/risks").json()
    assert (
        client.put(f"/api/v1/risks/{rows[0]['id']}", json=risk).json()["status"]
        == "resolved"
    )
    assert (
        client.post("/api/v1/risks", json={"title": "", "impact": 6}).status_code == 422
    )
    assert (
        client.post(
            "/api/v1/opportunities",
            json={"title": "Unsafe URL", "source_url": "javascript:alert(1)"},
        ).status_code
        == 422
    )


def test_routine_recurrence_checkin_and_undo(client):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("UTC")).date()
    data = {
        "title": "A small beginning",
        "start_date": today.isoformat(),
        "weekdays": [today.weekday()],
        "timezone": "UTC",
    }
    result = client.post("/api/v1/calendar/routines", json=data)
    assert result.status_code == 201, result.text
    routine_id = result.json()["id"]
    query = f"/api/v1/calendar/routine-occurrences?start={today}&end={today+timedelta(days=7)}"
    assert len(client.get(query).json()) == 2
    endpoint = f"/api/v1/calendar/routines/{routine_id}/checkins/{today}"
    assert client.put(endpoint, json={"status": "minimum"}).status_code == 200
    assert client.put(endpoint, json={"status": "done"}).status_code == 200
    assert client.get(query).json()[0]["status"] == "done"
    assert client.delete(endpoint).status_code == 204
    assert client.get(query).json()[0]["status"] == "pending"
    assert (
        client.put(
            f"/api/v1/calendar/routines/{routine_id}/checkins/{today+timedelta(days=7)}",
            json={"status": "done"},
        ).status_code
        == 422
    )


def test_invalid_routine_schedules_and_range(client):
    base = {"title": "Morning", "start_date": "2026-01-01"}
    for extra in (
        {"weekdays": []},
        {"weekdays": [7]},
        {"weekdays": [1, 1]},
        {"timezone": "Not/AZone"},
        {"minimum_minutes": 20},
        {"time_of_day": "25:00"},
        {"end_date": "2025-01-01"},
    ):
        assert (
            client.post("/api/v1/calendar/routines", json={**base, **extra}).status_code
            == 422
        )
    assert (
        client.get(
            "/api/v1/calendar/routine-occurrences?start=2026-01-01&end=2026-12-31"
        ).status_code
        == 422
    )


def test_dst_preserves_wall_time_and_skips_nonexistent_hour():
    from datetime import date
    from orin_api.models import Routine
    from orin_api.planning_domain import occurrence

    routine = Routine(
        start_date=date(2026, 1, 1),
        weekdays=list(range(7)),
        timezone="America/New_York",
        time_of_day="09:00",
    )
    assert occurrence(routine, date(2026, 3, 7)).hour == 14
    assert occurrence(routine, date(2026, 3, 8)).hour == 13
    routine.time_of_day = "02:30"
    assert occurrence(routine, date(2026, 3, 8)) is None


def test_pause_and_reminders_are_deduplicated(client, sessions, monkeypatch):
    from datetime import date, datetime, timezone
    from orin_api import background
    from orin_api.models import Notification

    factory, owner = sessions
    monkeypatch.setattr(background, "SessionLocal", factory)
    routine = client.post(
        "/api/v1/calendar/routines",
        json={
            "title": "One reminder",
            "start_date": "2026-01-01",
            "time_of_day": "09:00",
            "reminder_minutes": 5,
        },
    ).json()
    settings = Settings(_env_file=None)
    current = datetime(2026, 1, 5, 8, 56, tzinfo=timezone.utc)
    background.maintenance_tick(settings, now=current)
    background.maintenance_tick(settings, now=current)
    with factory() as session:
        assert len(session.scalars(select(Notification)).all()) == 1
    routine_id = routine.pop("id")
    routine["paused"] = True
    assert (
        client.put(f"/api/v1/calendar/routines/{routine_id}", json=routine).status_code
        == 200
    )
    assert (
        client.get(
            "/api/v1/calendar/routine-occurrences?start=2026-01-05&end=2026-01-05"
        ).json()
        == []
    )
    background.maintenance_tick(
        settings, now=datetime(2026, 1, 6, 8, 56, tzinfo=timezone.utc)
    )
    with factory() as session:
        assert len(session.scalars(select(Notification)).all()) == 1


def test_routine_occurrences_follow_calendar_display_timezone(client):
    routine = client.post(
        "/api/v1/calendar/routines",
        json={
            "title": "Late reflection",
            "start_date": "2026-01-01",
            "end_date": "2026-01-01",
            "timezone": "America/New_York",
            "time_of_day": "23:00",
        },
    )
    assert routine.status_code == 201
    response = client.get(
        "/api/v1/calendar/routine-occurrences?start=2026-01-02&end=2026-01-02&timezone=UTC"
    )
    assert len(response.json()) == 1
    assert response.json()[0]["day"] == "2026-01-01"
    assert (
        client.get(
            "/api/v1/calendar/routine-occurrences?start=2026-01-01&end=2026-01-01&timezone=invalid"
        ).status_code
        == 422
    )


def test_completed_opportunity_action_can_advance(client, sessions):
    from orin_api.models import Task, TaskStatus

    factory, owner = sessions
    opportunity = client.post(
        "/api/v1/opportunities",
        json={"title": "Build a connection", "next_action": "Read the brief"},
    ).json()
    endpoint = f"/api/v1/opportunities/{opportunity['id']}/next-task"
    first = client.post(endpoint).json()["task_id"]
    with factory.begin() as session:
        session.get(Task, uuid.UUID(first)).status = TaskStatus.DONE
    opportunity.pop("id")
    opportunity.pop("task_id")
    opportunity["next_action"] = "Draft a reply"
    item_id = client.get("/api/v1/opportunities").json()[0]["id"]
    assert (
        client.put(f"/api/v1/opportunities/{item_id}", json=opportunity).status_code
        == 200
    )
    second = client.post(endpoint).json()["task_id"]
    assert second != first
    assert client.post(endpoint).json()["task_id"] == second
