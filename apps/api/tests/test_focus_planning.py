from __future__ import annotations

import sqlite3
import uuid
import os
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from orin_api.auth import get_current_user
from orin_api import focus_router
from orin_api.config import Settings, get_settings
from orin_api.database import Base, get_session
from orin_api.focus_planning import select_now_task, select_todays_three
from orin_api.main import app
from orin_api.models import DailyPlan, EnergyLevel, FocusSession, FocusState, Task, TaskStatus, User


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    database_url = os.getenv("ORIN_FOCUS_TEST_DATABASE_URL")
    engine = create_engine(database_url or "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False} if not database_url else {},
        poolclass=StaticPool if not database_url else None)

    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection: sqlite3.Connection, _: object) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory.begin() as session:
        user = User(email="planning@example.test", password_hash="test-hash", display_name="Planner")
        session.add(user)
        session.flush()

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    app.state.planning_test_factory = factory
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        del app.state.planning_test_factory
        Base.metadata.drop_all(engine)
        engine.dispose()


def make_task(energy: EnergyLevel, *, title: str, touched_days_ago: int = 0,
              first_step: str | None = "Open the document", why: str | None = "Help the team",
              minutes: int | None = 10, status: TaskStatus = TaskStatus.TODO) -> Task:
    now = datetime.now(timezone.utc)
    task = Task(id=uuid.uuid4(), owner_id=uuid.uuid4(), title=title, energy_level=energy, last_touched_at=now - timedelta(days=touched_days_ago),
                first_step=first_step, why=why, estimated_minutes=minutes, status=status)
    return task


@pytest.mark.parametrize("energy", [EnergyLevel.LOW, EnergyLevel.MEDIUM, EnergyLevel.HIGH])
def test_todays_three_matches_energy_and_prefers_recent_context(energy: EnergyLevel) -> None:
    recent = make_task(energy, title="Recent", touched_days_ago=1)
    stale = make_task(energy, title="Stale", touched_days_ago=180)
    others = [make_task(energy, title=f"Other {index}", touched_days_ago=10 + index * 10) for index in range(3)]
    mismatched = make_task(EnergyLevel.HIGH if energy != EnergyLevel.HIGH else EnergyLevel.LOW, title="Wrong energy")
    done = make_task(energy, title="Done", status=TaskStatus.DONE)
    released = make_task(energy, title="Released", status=TaskStatus.CANCELLED)
    excluded = make_task(energy, title="Swapped away")
    candidates = [recent, stale, *others, mismatched, done, released, excluded]
    selected, anchor_id = select_todays_three(candidates, energy, excluded_ids={excluded.id})
    assert len(selected) == 3
    assert all(task.energy_level == energy for task in selected)
    assert recent in selected
    assert stale not in selected
    assert mismatched not in selected and done not in selected and released not in selected and excluded not in selected
    assert anchor_id in {task.id for task in selected}
    if energy == EnergyLevel.LOW:
        anchor = next(task for task in selected if task.id == anchor_id)
        assert anchor.estimated_minutes is not None and anchor.estimated_minutes <= 15


def test_low_energy_has_no_anchor_when_no_task_is_small_enough() -> None:
    large = make_task(EnergyLevel.LOW, title="Large low-energy task", minutes=20)
    selected, anchor_id = select_todays_three([large], EnergyLevel.LOW)
    assert selected == [large]
    assert anchor_id is None


def test_low_energy_anchor_is_kept_when_outside_top_three() -> None:
    long_tasks = [make_task(EnergyLevel.LOW, title=f"Long {index}", minutes=30) for index in range(3)]
    short_anchor = make_task(EnergyLevel.LOW, title="Short anchor", minutes=15)
    selected, anchor_id = select_todays_three([*long_tasks, short_anchor], EnergyLevel.LOW)
    assert len(selected) == 3
    assert selected[0] == short_anchor
    assert anchor_id == short_anchor.id


def test_task_estimates_break_ties_after_context_and_recent_activity() -> None:
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)
    tasks = [make_task(EnergyLevel.MEDIUM, title=f"Estimate {minutes}", minutes=minutes) for minutes in (10, 20, 30, 60)]
    for task in tasks:
        task.last_touched_at = now
    selected, _ = select_todays_three(tasks, EnergyLevel.MEDIUM)
    assert [task.estimated_minutes for task in selected] == [10, 20, 30]


def test_now_selection_obeys_active_anchor_and_position_order() -> None:
    first, anchor, active = (make_task(EnergyLevel.MEDIUM, title=name) for name in ("First", "Anchor", "Active"))
    no_active = select_now_task(None, [(first, False, 0), (anchor, True, 1), (active, False, 2)])
    assert no_active == anchor
    session = FocusSession(user_id=uuid.uuid4(), task_id=active.id, objective="Focus", duration_minutes=25, status="active")
    assert select_now_task(session, [(first, False, 0), (anchor, True, 1), (active, False, 2)]) == active
    completed_anchor = make_task(EnergyLevel.MEDIUM, title="Completed anchor", status=TaskStatus.DONE)
    assert select_now_task(None, [(completed_anchor, True, 0), (first, False, 2), (active, False, 1)]) == active


def test_capture_is_optional_and_creates_inbox_task(client: TestClient) -> None:
    response = client.post("/api/v1/focus/capture", json={})
    assert response.status_code == 201
    assert response.json()["title"] == "Untitled task"
    assert response.json()["status"] == "todo"
    assert response.json()["focus_state"] == "inbox"


def test_manual_today_selection_is_not_replaced_by_later_recommendations(client: TestClient) -> None:
    manual = client.post("/api/v1/tasks", json={"title": "Keep this choice", "energy_level": "low"}).json()
    recommended = client.post("/api/v1/tasks", json={"title": "Higher energy option", "energy_level": "high"}).json()
    assert client.put("/api/v1/focus/today/tasks", json={"tasks": [{"task_id": manual["id"], "is_anchor": True}]}).status_code == 200
    assert client.put("/api/v1/focus/energy", json={"energy_level": "high"}).status_code == 200
    proposed = client.post("/api/v1/focus/today/propose")
    assert proposed.status_code == 200
    assert [task["id"] for task in proposed.json()["tasks"]] == [manual["id"]]
    assert recommended["id"] not in {task["id"] for task in proposed.json()["tasks"]}


def test_capture_suggestions_are_optional_and_do_not_persist_tasks(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class Provider:
        def structured_output(self, *, system: str, user: str, model: str, schema: dict[str, object], images: list[dict[str, str]] | None = None) -> str:
            assert "untrusted task data" in system
            assert '"captured_text": "Write the report"' in user
            return '{"title":"Draft the report","first_step":"Open a blank document","energy_level":"low"}'

    monkeypatch.setattr(focus_router, "create_provider", lambda _: Provider())
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, ai_provider="openai", ai_model="test-model")
    suggestion = client.post("/api/v1/focus/capture/suggest", json={"title": "Write the report"})
    assert suggestion.status_code == 200
    assert suggestion.json() == {"title": "Draft the report", "first_step": "Open a blank document", "energy_level": "low"}
    assert client.get("/api/v1/focus/later").json() == []
    captured = client.post("/api/v1/focus/capture", json={"title": suggestion.json()["title"],
        "first_step": suggestion.json()["first_step"], "energy_level": suggestion.json()["energy_level"]})
    assert captured.status_code == 201
    assert captured.json()["first_step"] == "Open a blank document"
    assert captured.json()["energy_level"] == "low"


def test_smaller_step_suggestion_and_unavailable_ai_leave_manual_path_open(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class Provider:
        def structured_output(self, *, system: str, user: str, model: str, schema: dict[str, object], images: list[dict[str, str]] | None = None) -> str:
            return '{"first_step":"Open the file"}'

    monkeypatch.setattr(focus_router, "create_provider", lambda _: Provider())
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, ai_provider="openai", ai_model="test-model")
    result = client.post("/api/v1/focus/suggest-smaller", json={"title": "Plan the proposal", "first_step": "Write the whole draft"})
    assert result.status_code == 200
    assert result.json() == {"first_step": "Open the file"}

    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    unavailable = client.post("/api/v1/focus/capture/suggest", json={"title": "Plan the proposal"})
    assert unavailable.status_code == 503
    assert "continue manually" in unavailable.json()["detail"]
    assert client.post("/api/v1/focus/capture", json={"title": "Plan the proposal"}).status_code == 201

    class MalformedProvider:
        def structured_output(self, *, system: str, user: str, model: str, schema: dict[str, object], images: list[dict[str, str]] | None = None) -> str:
            return '{"title":"No first step"}'

    monkeypatch.setattr(focus_router, "create_provider", lambda _: MalformedProvider())
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, ai_provider="openai", ai_model="test-model")
    malformed = client.post("/api/v1/focus/capture/suggest", json={"title": "Plan another proposal"})
    assert malformed.status_code == 503
    assert "invalid suggestion" in malformed.json()["detail"]
    assert client.post("/api/v1/focus/capture", json={"title": "Plan another proposal"}).status_code == 201


def test_now_starts_task_linked_focus_and_advances_after_completion(client: TestClient) -> None:
    captured = client.post("/api/v1/focus/capture", json={"title": "Prepare the outline"}).json()
    client.put("/api/v1/focus/today/tasks", json={"tasks": [{"task_id": captured["id"], "is_anchor": True}]})
    assert client.get("/api/v1/focus/now").json()["task"]["id"] == captured["id"]
    started = client.post("/api/v1/focus/now/start", json={})
    assert started.status_code == 200
    assert started.json()["focus_session"]["task_id"] == captured["id"]
    assert client.get("/api/v1/focus/now").json()["focus_session"]["task_id"] == captured["id"]
    completed = client.post("/api/v1/focus/now/complete", json={})
    assert completed.status_code == 200
    assert completed.json()["empty_state"] is True


def test_two_swaps_are_allowed_then_rest_is_offered_and_day_key_resets(client: TestClient) -> None:
    created = client.post("/api/v1/tasks", json={"title": "Anchor", "energy_level": "low", "estimated_minutes": 10})
    anchor_id = created.json()["id"]
    candidates = []
    for title in ("Later one", "Later two"):
        task = client.post("/api/v1/tasks", json={"title": title, "energy_level": "low", "status": "in_progress"}).json()
        client.patch(f"/api/v1/tasks/{task['id']}", json={"status": "todo"})
        candidates.append(task["id"])
    client.put("/api/v1/focus/energy", json={"energy_level": "low"})

    factory = app.state.planning_test_factory
    with factory.begin() as session:
        # A previous local day with two swaps must not consume today's allowance.
        session.add(DailyPlan(user_id=app.dependency_overrides[get_current_user]().id,
            day_key="2000-01-01", swapped_task_ids=[str(uuid.uuid4()), str(uuid.uuid4())]))
    assert client.put("/api/v1/focus/today/tasks", json={"tasks": [{"task_id": anchor_id, "is_anchor": True}]}).status_code == 200
    assert client.post("/api/v1/focus/today/swap").json()["swapped"] is True
    assert client.post("/api/v1/focus/today/swap").json()["swapped"] is True
    limited = client.post("/api/v1/focus/today/swap").json()
    assert limited["limit_reached"] is True
    assert limited["rest_available"] is True
    assert limited["message"] == "Let's stay with this one, or rest."


def test_retrying_a_swap_request_does_not_swap_the_replacement_again(client: TestClient) -> None:
    anchor = client.post("/api/v1/tasks", json={"title": "Anchor", "energy_level": "low", "estimated_minutes": 10}).json()
    candidates = []
    for title in ("First replacement", "Second replacement", "Third replacement"):
        task = client.post("/api/v1/tasks", json={"title": title, "energy_level": "low", "status": "in_progress"}).json()
        client.patch(f"/api/v1/tasks/{task['id']}", json={"status": "todo"})
        candidates.append(task["id"])
    client.put("/api/v1/focus/energy", json={"energy_level": "low"})
    client.put("/api/v1/focus/today/tasks", json={"tasks": [{"task_id": anchor["id"], "is_anchor": True}]})

    first = client.post("/api/v1/focus/today/swap", json={"task_id": anchor["id"]}).json()
    assert first["swapped"] is True
    replacement_id = first["task"]["id"]
    retry = client.post("/api/v1/focus/today/swap", json={"task_id": anchor["id"]}).json()
    assert retry["swapped"] is False
    assert retry["already_swapped"] is True
    assert client.get("/api/v1/focus/now").json()["task"]["id"] == replacement_id

    second = client.post("/api/v1/focus/today/swap", json={"task_id": replacement_id}).json()
    assert second["swapped"] is True
    limited = client.post("/api/v1/focus/today/swap", json={"task_id": second["task"]["id"]}).json()
    assert limited["limit_reached"] is True


@pytest.mark.skipif(not os.getenv("ORIN_FOCUS_TEST_DATABASE_URL"), reason="requires an isolated PostgreSQL test database")
def test_concurrent_swap_requests_obey_daily_limit(client: TestClient) -> None:
    anchor = client.post("/api/v1/tasks", json={"title": "Anchor", "energy_level": "low", "estimated_minutes": 10}).json()
    for title in ("Replacement one", "Replacement two", "Replacement three"):
        task = client.post("/api/v1/tasks", json={"title": title, "energy_level": "low", "status": "in_progress"}).json()
        client.patch(f"/api/v1/tasks/{task['id']}", json={"status": "todo"})
    client.put("/api/v1/focus/energy", json={"energy_level": "low"})
    client.put("/api/v1/focus/today/tasks", json={"tasks": [{"task_id": anchor["id"], "is_anchor": True}]})

    def concurrent_posts(payload: dict[str, str] | None) -> list[dict[str, object]]:
        barrier = Barrier(2)
        def send() -> dict[str, object]:
            barrier.wait(timeout=5)
            return client.post("/api/v1/focus/today/swap", json=payload or {}).json()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(lambda _: send(), range(2)))

    duplicate_requests = concurrent_posts({"task_id": anchor["id"]})
    assert sum(result["swapped"] is True for result in duplicate_requests) == 1
    assert sum(result.get("already_swapped") is True for result in duplicate_requests) == 1

    final_allowance = concurrent_posts(None)
    assert sum(result["swapped"] is True for result in final_allowance) == 1
    assert sum(result["limit_reached"] is True for result in final_allowance) == 1
