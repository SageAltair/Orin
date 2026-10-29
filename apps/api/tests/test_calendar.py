from datetime import date
import sqlite3
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from orin_api.auth import get_current_user
from orin_api.database import Base, get_session
from orin_api.main import app
from orin_api.models import CalendarEvent, User


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection: sqlite3.Connection, _: object) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions.begin() as session:
        user = User(email="morgan@example.test", password_hash="test-hash", display_name="Morgan")
        session.add(user)
        session.flush()

    def override_session() -> Generator:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_timed_events_are_owner_scoped_and_returned_for_local_day(client: TestClient) -> None:
    created = client.post("/api/v1/calendar/events", json={
        "title": "Evening call",
        "start_at": "2026-10-10T23:30:00+03:00",
        "end_at": "2026-10-11T00:15:00+03:00",
        "timezone": "Africa/Dar_es_Salaam",
    })
    assert created.status_code == 201
    event = created.json()
    assert event["start_at"] == "2026-10-10T20:30:00Z"
    assert event["timezone"] == "Africa/Dar_es_Salaam"

    next_day = client.get("/api/v1/calendar/events", params={
        "start": "2026-10-11", "end": "2026-10-11", "timezone": "Africa/Dar_es_Salaam",
    })
    assert [row["id"] for row in next_day.json()] == [event["id"]]

    session_factory = app.dependency_overrides[get_session]
    session_generator = session_factory()
    session = next(session_generator)
    try:
        owner = session.query(User).filter_by(email="morgan@example.test").one()
        stranger = User(email="stranger@example.test", password_hash="test", display_name="Stranger")
        session.add(stranger)
        session.flush()
        foreign = CalendarEvent(user_id=stranger.id, title="Private", is_all_day=True,
            start_date=date(2026, 10, 10), end_date=date(2026, 10, 10), timezone="UTC")
        session.add(foreign)
        session.commit()
        assert foreign.user_id != owner.id
        foreign_id = foreign.id
    finally:
        session.close()
    assert client.get("/api/v1/calendar/events", params={"start": "2026-10-10", "end": "2026-10-11", "timezone": "Africa/Dar_es_Salaam"}).json() == [event]
    assert client.patch(f"/api/v1/calendar/events/{foreign_id}", json={"title": "Tamper"}).status_code == 404


def test_all_day_events_keep_calendar_dates_and_support_edit_delete(client: TestClient) -> None:
    created = client.post("/api/v1/calendar/events", json={
        "title": "Workshop", "is_all_day": True,
        "start_date": "2026-03-08", "end_date": "2026-03-09",
        "timezone": "America/Los_Angeles",
    })
    assert created.status_code == 201
    event = created.json()
    assert event["start_date"] == "2026-03-08"
    assert event["end_date"] == "2026-03-09"
    assert event["start_at"] is None

    patched = client.patch(f"/api/v1/calendar/events/{event['id']}", json={"description": "Bring notes"})
    assert patched.status_code == 200
    assert patched.json()["description"] == "Bring notes"
    assert patched.json()["start_date"] == "2026-03-08"
    assert client.delete(f"/api/v1/calendar/events/{event['id']}").status_code == 204
    assert client.get("/api/v1/calendar/events", params={"start": "2026-03-08", "end": "2026-03-09"}).json() == []


def test_calendar_event_reminder_offsets_are_optional_persisted_preferences(client: TestClient) -> None:
    event = client.post("/api/v1/calendar/events", json={
        "title": "Reminder preference", "is_all_day": False,
        "start_at": "2026-10-12T09:00:00+03:00", "end_at": "2026-10-12T10:00:00+03:00",
        "timezone": "Africa/Dar_es_Salaam", "reminder_minutes": 15,
    })
    assert event.status_code == 201, event.text
    event_id = event.json()["id"]
    assert event.json()["reminder_minutes"] == 15
    invalid = client.patch(f"/api/v1/calendar/events/{event_id}", json={"reminder_minutes": 7})
    assert invalid.status_code == 422
    cleared = client.patch(f"/api/v1/calendar/events/{event_id}", json={"reminder_minutes": None})
    assert cleared.status_code == 200
    assert cleared.json()["reminder_minutes"] is None


def test_event_validation_requires_consistent_dates_and_offsets(client: TestClient) -> None:
    no_offset = client.post("/api/v1/calendar/events", json={
        "title": "Call", "start_at": "2026-10-10T09:00:00", "end_at": "2026-10-10T10:00:00",
    })
    assert no_offset.status_code == 422

    reversed_event = client.post("/api/v1/calendar/events", json={
        "title": "Call", "start_at": "2026-10-10T10:00:00Z", "end_at": "2026-10-10T09:00:00Z",
    })
    assert reversed_event.status_code == 422

    mixed = client.post("/api/v1/calendar/events", json={
        "title": "Call", "is_all_day": True, "start_date": "2026-10-10", "end_date": "2026-10-11",
        "start_at": "2026-10-10T10:00:00Z", "end_at": "2026-10-10T11:00:00Z",
    })
    assert mixed.status_code == 422


def test_event_range_rejects_invalid_timezone_and_excessive_windows(client: TestClient) -> None:
    assert client.get("/api/v1/calendar/events", params={"start": "2026-01-01", "end": "2027-12-31"}).status_code == 422
    assert client.get("/api/v1/calendar/events", params={"start": "2026-01-01", "end": "2026-01-02", "timezone": "Mars/Olympus"}).status_code == 422


def test_task_schedule_conflict_retry_reschedule_and_unschedule_preserve_task(client: TestClient) -> None:
    task_response = client.post("/api/v1/tasks", json={"title": "Draft proposal", "due_at": "2026-10-20T00:00:00Z"})
    assert task_response.status_code == 201
    task = task_response.json()
    client.post("/api/v1/calendar/events", json={
        "title": "Planning call", "start_at": "2026-10-20T09:00:00+03:00",
        "end_at": "2026-10-20T10:00:00+03:00", "timezone": "Africa/Dar_es_Salaam",
    })
    block_data = {"start_at": "2026-10-20T09:30:00+03:00", "end_at": "2026-10-20T10:00:00+03:00",
        "estimated_minutes": 30, "timezone": "Africa/Dar_es_Salaam"}
    conflict = client.put(f"/api/v1/calendar/tasks/{task['id']}/schedule", json=block_data)
    assert conflict.status_code == 409
    assert "Planning call" in conflict.json()["detail"]["conflicts"][0]["title"]

    block_data["allow_overlap"] = True
    scheduled = client.put(f"/api/v1/calendar/tasks/{task['id']}/schedule", json=block_data)
    assert scheduled.status_code == 200
    assert scheduled.json()["task_id"] == task["id"]
    moved = {**block_data, "start_at": "2026-10-21T09:00:00+03:00", "end_at": "2026-10-21T09:30:00+03:00"}
    assert client.put(f"/api/v1/calendar/tasks/{task['id']}/schedule", json=moved).json()["start_at"] == "2026-10-21T06:00:00Z"
    assert len(client.get("/api/v1/calendar/schedule", params={"start": "2026-10-20", "end": "2026-10-21", "timezone": "Africa/Dar_es_Salaam"}).json()) == 1
    assert client.delete(f"/api/v1/calendar/tasks/{task['id']}/schedule").status_code == 204
    remaining = client.get("/api/v1/tasks").json()[0]
    assert remaining["id"] == task["id"]
    assert remaining["status"] == "todo"
    assert remaining["due_at"].startswith("2026-10-20T00:00:00")


def test_completing_a_scheduled_task_uses_existing_task_flow_and_releases_block(client: TestClient) -> None:
    task = client.post("/api/v1/tasks", json={"title": "Review report"}).json()
    scheduled = client.put(f"/api/v1/calendar/tasks/{task['id']}/schedule", json={
        "start_at": "2026-10-20T09:00:00Z", "end_at": "2026-10-20T10:00:00Z",
        "estimated_minutes": 60, "timezone": "UTC",
    })
    assert scheduled.status_code == 200
    completed = client.patch(f"/api/v1/tasks/{task['id']}", json={"status": "done"})
    assert completed.status_code == 200 and completed.json()["status"] == "done"
    assert client.get("/api/v1/calendar/schedule", params={"start": "2026-10-20", "end": "2026-10-20"}).json() == []
