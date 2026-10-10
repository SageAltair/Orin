from __future__ import annotations

import importlib.util
import ast
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from orin_api.auth import get_current_user
from orin_api.database import Base, get_session
from orin_api.focus_domain import complete_task, local_day_key, release_task, reopen_task
from orin_api.main import app
from orin_api.models import DailyClose, DailyPlan, DailyPlanTask, DriftEvent, DriftTrigger, EnergyLevel, FocusSession, Task, TaskStatus, User, UserSettings


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection: sqlite3.Connection, _: object) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with test_sessions.begin() as session:
        primary = User(email="focus-primary@example.test", password_hash="test-hash", display_name="Primary")
        second = User(email="focus-second@example.test", password_hash="test-hash", display_name="Second")
        session.add_all([primary, second])
        session.flush()
        other_task = Task(owner_id=second.id, title="Second user's task")
        session.add(other_task)
        session.flush()

    active_user = [primary]

    def override_session() -> Generator[Session, None, None]:
        with test_sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: active_user[0]
    app.state.focus_test_users = (primary, second, other_task, active_user)
    app.state.focus_test_session_factory = test_sessions
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        del app.state.focus_test_users
        del app.state.focus_test_session_factory
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_local_day_key_uses_four_am_boundary_and_iana_dst_rules() -> None:
    assert local_day_key(datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc), "UTC") == "2026-10-09"
    assert local_day_key(datetime(2026, 10, 10, 3, 59, tzinfo=timezone.utc), "UTC") == "2026-10-09"
    assert local_day_key(datetime(2026, 10, 10, 4, 0, tzinfo=timezone.utc), "UTC") == "2026-10-10"
    # On the spring-forward day New York jumps over 02:00; 04:00 local still rolls the day.
    assert local_day_key(datetime(2026, 3, 8, 7, 59, tzinfo=timezone.utc), "America/New_York") == "2026-03-07"
    assert local_day_key(datetime(2026, 3, 8, 8, 0, tzinfo=timezone.utc), "America/New_York") == "2026-03-08"
    # The autumn repeated hour remains on the previous local day until 04:00.
    assert local_day_key(datetime(2026, 11, 1, 8, 59, tzinfo=timezone.utc), "America/New_York") == "2026-10-31"
    assert local_day_key(datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc), "America/New_York") == "2026-11-01"


def test_task_lifecycle_transitions_keep_legacy_status_and_focus_state_consistent() -> None:
    task = Task(owner_id=uuid.uuid4(), title="Draft outline")
    complete_task(task, now=datetime(2026, 10, 10, tzinfo=timezone.utc))
    assert task.status == TaskStatus.DONE
    assert task.focus_state is None
    assert task.completed_at == datetime(2026, 10, 10, tzinfo=timezone.utc)

    reopen_task(task, now=datetime(2026, 10, 11, tzinfo=timezone.utc))
    assert task.status == TaskStatus.TODO
    assert task.focus_state.value == "later"
    assert task.completed_at is None

    release_task(task, now=datetime(2026, 10, 12, tzinfo=timezone.utc))
    assert task.status == TaskStatus.CANCELLED
    assert task.focus_state.value == "released"
    assert task.released_at == datetime(2026, 10, 12, tzinfo=timezone.utc)


def test_migration_backfills_legacy_task_states_without_changing_status() -> None:
    migration_path = Path(__file__).parents[1] / "migrations" / "versions" / "20261010_focus_foundation.py"
    spec = importlib.util.spec_from_file_location("focus_foundation_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE tasks (status VARCHAR(20), created_at DATETIME, updated_at DATETIME, focus_state VARCHAR(20), last_touched_at DATETIME, decay_review_at DATETIME, completed_at DATETIME, released_at DATETIME)"))
        created = "2026-01-01 08:00:00"
        rows = [("todo", created, "2026-01-02 08:00:00"), ("in_progress", created, created),
                ("blocked", created, created), ("done", created, "2026-01-03 08:00:00"),
                ("cancelled", created, "2026-01-04 08:00:00")]
        connection.execute(text("INSERT INTO tasks(status, created_at, updated_at) VALUES (:s, :c, :u)"),
                           [{"s": s, "c": c, "u": u} for s, c, u in rows])
        migration.backfill_task_focus_state(connection)
        mapped = connection.execute(text("SELECT status, focus_state, last_touched_at, completed_at, released_at FROM tasks ORDER BY rowid")).all()
        assert [row.status for row in mapped] == ["todo", "in_progress", "blocked", "done", "cancelled"]
        assert [row.focus_state for row in mapped] == ["later", "active", "later", None, "released"]
        assert mapped[3].completed_at == "2026-01-03 08:00:00"
        assert mapped[4].released_at == "2026-01-04 08:00:00"
        assert mapped[0].last_touched_at == "2026-01-02 08:00:00"
    engine.dispose()


def test_focus_records_are_owner_scoped_and_privacy_delete_is_scoped(client: TestClient) -> None:
    primary, second, other_task, active_user = app.state.focus_test_users
    own_task = client.post("/api/v1/tasks", json={"title": "Primary task"}).json()
    assert client.post("/api/v1/focus-sessions", json={"task_id": str(other_task.id), "objective": "Focus", "duration_minutes": 25}).status_code == 404
    active_user[0] = second
    second_focus = client.post("/api/v1/focus-sessions", json={"task_id": str(other_task.id), "objective": "Focus", "duration_minutes": 25})
    assert second_focus.status_code == 201
    active_user[0] = primary
    assert client.post("/api/v1/focus/drift", json={"focus_session_id": second_focus.json()["id"], "trigger_type": "tired"}).status_code == 404
    own_drift = client.post("/api/v1/focus/drift", json={"task_id": own_task["id"], "trigger_type": "thought", "note": "Private reflection"})
    assert own_drift.status_code == 201
    own_close = client.put("/api/v1/focus/daily-closes/today", json={"reflection": "A private daily note"})
    assert own_close.status_code == 200
    factory = app.state.focus_test_session_factory
    with factory.begin() as session:
        plan = DailyPlan(user_id=primary.id, day_key="2026-10-10", energy_level=EnergyLevel.LOW)
        session.add(plan)
        session.flush()
        session.add(DailyPlanTask(user_id=primary.id, plan_id=plan.id, task_id=uuid.UUID(own_task["id"]), position=0, is_anchor=True))

    active_user[0] = second
    settings = client.put("/api/v1/focus/settings", json={"timezone": "Africa/Dar_es_Salaam", "energy_today": "low"})
    assert settings.status_code == 200
    assert client.post("/api/v1/focus/drift", json={"task_id": own_task["id"], "trigger_type": "tired"}).status_code == 404
    assert client.put("/api/v1/focus/daily-closes/today", json={"tomorrow_task_id": own_task["id"]}).status_code == 404
    other_drift = client.post("/api/v1/focus/drift", json={"task_id": str(other_task.id), "trigger_type": "app"})
    assert other_drift.status_code == 201
    other_close = client.put("/api/v1/focus/daily-closes/today", json={"reflection": "Second user's private note"})
    assert other_close.status_code == 200

    active_user[0] = primary
    assert len(client.get("/api/v1/focus/drift").json()) == 1
    assert len(client.get("/api/v1/focus/daily-closes").json()) == 1
    export = client.get("/api/v1/focus/privacy/export").json()
    assert len(export["drift_events"]) == 1
    assert len(export["daily_closes"]) == 1
    assert export["user_settings"]["timezone"] == "UTC"
    assert len(export["daily_plans"]) == 1
    assert export["daily_plans"][0]["energy_level"] == "low"
    assert export["daily_plan_tasks"] == [{"plan_id": export["daily_plans"][0]["id"], "task_id": own_task["id"], "position": 0, "is_anchor": True}]
    assert client.delete("/api/v1/focus/privacy/data").status_code == 204
    assert client.get("/api/v1/focus/privacy/export").json()["daily_plans"] == []
    assert client.get("/api/v1/focus/drift").json() == []
    active_user[0] = second
    assert len(client.get("/api/v1/focus/drift").json()) == 1
    assert len(client.get("/api/v1/focus/daily-closes").json()) == 1
    assert client.get("/api/v1/focus/settings").json()["timezone"] == "Africa/Dar_es_Salaam"


def test_focus_read_routes_and_plan_writes_are_scoped_to_active_user(client: TestClient) -> None:
    primary, second, other_task, active_user = app.state.focus_test_users
    primary_task = client.post("/api/v1/focus/capture", json={"title": "Primary plan task"}).json()
    assert client.put("/api/v1/focus/energy", json={"energy_level": "low"}).status_code == 200
    assert client.put("/api/v1/focus/today/tasks", json={"tasks": [{"task_id": primary_task["id"], "is_anchor": True}]}).status_code == 200
    active_user[0] = second
    assert client.get("/api/v1/focus/today").json()["tasks"] == []
    assert client.get("/api/v1/focus/now").json()["task"] is None
    assert client.get("/api/v1/focus/later").json()[0]["id"] == str(other_task.id)
    assert client.get("/api/v1/focus/drift").json() == []
    assert client.get("/api/v1/focus/daily-closes").json() == []
    assert client.get("/api/v1/focus/close/today").json()["done_list"] == []
    assert client.get("/api/v1/focus/privacy/export").json()["daily_plan_tasks"] == []
    assert client.put("/api/v1/focus/today/tasks", json={"tasks": [{"task_id": primary_task["id"]}]}).status_code == 404
    assert client.put("/api/v1/focus/daily-closes/today", json={"tomorrow_task_id": primary_task["id"]}).status_code == 404
    active_user[0] = primary
    assert client.delete("/api/v1/focus/privacy/data").status_code == 204
    with app.state.focus_test_session_factory() as session:
        assert session.scalar(select(DailyPlanTask).where(DailyPlanTask.user_id == second.id)) is None


def test_every_focus_table_is_scoped_by_user_id(client: TestClient) -> None:
    primary, second, _, _ = app.state.focus_test_users
    factory = app.state.focus_test_session_factory
    with factory() as session:
        for owner, suffix in ((primary, "one"), (second, "two")):
            task = Task(owner_id=owner.id, title=f"Task {suffix}")
            session.add(task)
            session.flush()
            session.add_all([
                UserSettings(user_id=owner.id, timezone="UTC"),
                DailyPlan(id=uuid.uuid4(), user_id=owner.id, day_key=f"2026-10-0{1 if suffix == 'one' else 2}", energy_level=EnergyLevel.LOW),
                DriftEvent(user_id=owner.id, task_id=task.id, day_key="2026-10-10", trigger_type=DriftTrigger.OTHER, note="private"),
                DailyClose(user_id=owner.id, day_key=f"2026-10-0{1 if suffix == 'one' else 2}", reflection="private"),
            ])
            session.flush()
            plan = session.scalar(select(DailyPlan).where(DailyPlan.user_id == owner.id))
            session.add(DailyPlanTask(user_id=owner.id, plan_id=plan.id, task_id=task.id, position=0))
            session.add(FocusSession(user_id=owner.id, task_id=task.id, project_id=None, objective="Focus", duration_minutes=25, status="completed"))
        session.flush()
        for model in (UserSettings, DailyPlan, DailyPlanTask, DriftEvent, DailyClose, FocusSession):
            rows = session.scalars(select(model).where(model.user_id == primary.id)).all()
            assert rows and all(row.user_id == primary.id for row in rows)
            assert len(session.scalars(select(model).where(model.user_id == second.id)).all()) >= 1


def test_task_status_and_focus_state_writes_are_confined_to_domain_service() -> None:
    source_root = Path(__file__).parents[1] / "src" / "orin_api"
    findings: list[str] = []
    for source_path in source_root.glob("*.py"):
        if source_path.name == "focus_domain.py":
            continue
        tree = ast.parse(source_path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute) and target.attr in {"status", "focus_state"} and isinstance(target.value, ast.Name) and target.value.id == "task":
                    findings.append(f"{source_path.name}:{node.lineno} writes task.{target.attr}")
    assert findings == []


def test_drift_and_reflection_validation_never_echoes_sensitive_text(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    sentinel = "PRIVATE-DRIFT-AND-REFLECTION-SENTINEL"
    oversized = sentinel + ("x" * 4100)
    with caplog.at_level(logging.INFO, logger="orin_api.request"):
        drift = client.post("/api/v1/focus/drift", json={"trigger_type": "other", "note": oversized})
        close = client.put("/api/v1/focus/daily-closes/today", json={"reflection": oversized})
    assert drift.status_code == close.status_code == 422
    assert sentinel not in caplog.text
    assert sentinel not in drift.text
    assert sentinel not in close.text


def test_focus_write_routes_reject_invalid_and_unknown_inputs(client: TestClient) -> None:
    task = client.post("/api/v1/focus/capture", json={"title": "Validated task"}).json()
    assert client.post("/api/v1/focus/capture", json={"title": "x" * 241}).status_code == 422
    assert client.post("/api/v1/focus/capture", json={"title": "valid", "surprise": True}).status_code == 422
    assert client.put("/api/v1/focus/energy", json={"energy_level": "unknown"}).status_code == 422
    assert client.put("/api/v1/focus/energy", json={"energy_level": "low", "extra": 1}).status_code == 422
    assert client.put("/api/v1/focus/settings", json={"timezone": "Mars/Olympus"}).status_code == 422
    assert client.put("/api/v1/focus/settings", json={"unexpected": True}).status_code == 422
    too_many = [{"task_id": task["id"]} for _ in range(4)]
    assert client.put("/api/v1/focus/today/tasks", json={"tasks": too_many}).status_code == 422
    assert client.put("/api/v1/focus/today/tasks", json={"tasks": [{"task_id": task["id"], "unknown": 1}]}).status_code == 422
    assert client.post("/api/v1/focus/drift", json={"trigger_type": "unknown"}).status_code == 422
    assert client.post("/api/v1/focus/drift", json={"trigger_type": "other", "unknown": 1}).status_code == 422
    assert client.put("/api/v1/focus/daily-closes/today", json={"drift_triggers": ["unknown"]}).status_code == 422
    assert client.put("/api/v1/focus/daily-closes/today", json={"unknown": 1}).status_code == 422


def test_progress_reentry_is_shown_once_and_rest_day_is_neutral(client: TestClient) -> None:
    primary, _, _, _ = app.state.focus_test_users
    today = datetime.now(timezone.utc).date()
    old_day = (today - timedelta(days=4)).isoformat()
    with app.state.focus_test_session_factory.begin() as session:
        session.add(UserSettings(user_id=primary.id, timezone="UTC", last_seen_day_key=old_day))
    first = client.get("/api/v1/focus/progress").json()
    assert first["reentry"]["show"] is True
    assert first["completed_days"] == 0
    assert client.get("/api/v1/focus/progress").json()["reentry"]["show"] is True
    assert client.post("/api/v1/focus/reentry/dismiss").status_code == 204
    assert client.get("/api/v1/focus/progress").json()["reentry"]["show"] is False

    today_weekday = today.weekday()
    assert client.put("/api/v1/focus/settings", json={"weekly_rest_day": today_weekday}).status_code == 200
    rested = client.get("/api/v1/focus/now").json()
    assert rested["rest_day"] is True
    assert rested["task"] is None
    assert client.post("/api/v1/focus/capture", json={"title": "A rest-day thought"}).status_code == 201


def test_decay_review_lists_only_owned_tasks_and_applies_all_outcomes(client: TestClient) -> None:
    primary, second, _, _ = app.state.focus_test_users
    past = datetime.now(timezone.utc) - timedelta(days=1)
    tasks = [Task(owner_id=primary.id, title=f"Review {name}", focus_state="later", decay_review_at=past)
             for name in ("keep", "shrink", "release")]
    hidden = Task(owner_id=second.id, title="Other review", focus_state="later", decay_review_at=past)
    with app.state.focus_test_session_factory.begin() as session:
        session.add_all([*tasks, hidden])
    candidates = client.get("/api/v1/focus/review").json()
    ids = {row["id"] for row in candidates}
    assert str(hidden.id) not in ids
    by_title = {row["title"]: row["id"] for row in candidates}
    for title, payload in (("Review keep", {"outcome": "keep"}),
                           ("Review shrink", {"outcome": "shrink", "first_step": "One small line"}),
                           ("Review release", {"outcome": "release"})):
        result = client.post(f"/api/v1/focus/review/{by_title[title]}", json=payload)
        assert result.status_code == 200
        if payload["outcome"] == "release":
            assert result.json()["task"]["status"] == "cancelled"
        elif payload["outcome"] == "shrink":
            assert result.json()["task"]["first_step"] == "One small line"
        else:
            assert datetime.fromisoformat(result.json()["task"]["decay_review_at"]) > datetime.now(timezone.utc)
    assert client.post(f"/api/v1/focus/review/{hidden.id}", json={"outcome": "keep"}).status_code == 404


def test_focus_mode_drift_links_active_task_and_session(client: TestClient) -> None:
    task = client.post("/api/v1/focus/capture", json={"title": "Focus drift linkage"}).json()
    assert client.put("/api/v1/focus/today/tasks", json={"tasks": [{"task_id": task["id"], "is_anchor": True}]}).status_code == 200
    started = client.post("/api/v1/focus/now/start", json={})
    assert started.status_code == 200
    focus_id = started.json()["focus_session"]["id"]
    drift = client.post("/api/v1/focus/now/drift", json={"task_id": task["id"], "focus_session_id": focus_id})
    assert drift.status_code == 201
    assert drift.json()["task_id"] == task["id"]
    assert drift.json()["focus_session_id"] == focus_id
    assert len(client.get("/api/v1/focus/drift").json()) == 1


def test_settings_routines_and_prompt_caps_are_validated_and_persisted(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import orin_api.focus_router as focus_router

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz: timezone | None = None) -> datetime:
            instant = datetime(2026, 10, 10, 8, 10, tzinfo=timezone.utc)
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

    monkeypatch.setattr(focus_router, "datetime", FixedDateTime)
    settings = client.put("/api/v1/focus/settings", json={
        "timezone": "UTC", "default_energy": "low", "weekly_rest_day": 6,
        "check_in_interval": 25, "quiet_hours": {"start": "22:00", "end": "07:00"},
        "routines": [{"name": "coffee", "time": "08:00"}], "body_doubling_enabled": True,
        "accountability_contact": "morgan@example.test"})
    assert settings.status_code == 200
    assert client.get("/api/v1/focus/settings").json()["routines"] == [{"name": "coffee", "time": "08:00"}]
    assert client.put("/api/v1/focus/settings", json={"quiet_hours": {"start": "22:88", "end": "07:00"}}).status_code == 422
    assert client.put("/api/v1/focus/settings", json={"check_in_interval": 2}).status_code == 422
    task = Task(owner_id=app.state.focus_test_users[0].id, title="Routine task", focus_state="later", trigger="after coffee")
    with app.state.focus_test_session_factory.begin() as session:
        session.add(task)
    forms = [client.get("/api/v1/focus/prompts").json()["items"][0]["form"] for _ in range(3)]
    assert forms == ["gentle", "softer", "visual_on_open"]
    assert client.get("/api/v1/focus/prompts").json()["items"] == []


def test_legacy_task_status_api_uses_shared_focus_transitions(client: TestClient) -> None:
    created = client.post("/api/v1/tasks", json={"title": "Transition task"})
    assert created.status_code == 201
    task_id = created.json()["id"]
    assert created.json()["status"] == "todo"
    assert created.json()["focus_state"] == "inbox"

    completed = client.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"}).json()
    assert completed["status"] == "done"
    assert completed["focus_state"] is None
    assert completed["completed_at"] is not None

    reopened = client.patch(f"/api/v1/tasks/{task_id}", json={"status": "todo"}).json()
    assert reopened["status"] == "todo"
    assert reopened["focus_state"] == "later"
    assert reopened["completed_at"] is None

    released = client.patch(f"/api/v1/tasks/{task_id}", json={"status": "cancelled"}).json()
    assert released["status"] == "cancelled"
    assert released["focus_state"] == "released"
    assert released["released_at"] is not None


def test_first_settings_read_uses_browser_timezone_only_when_unset(client: TestClient) -> None:
    assert client.get("/api/v1/focus/settings", headers={"X-Timezone": "Africa/Dar_es_Salaam"}).json()["timezone"] == "Africa/Dar_es_Salaam"
    assert client.get("/api/v1/focus/settings", headers={"X-Timezone": "America/Los_Angeles"}).json()["timezone"] == "Africa/Dar_es_Salaam"
