"""Measure core focus API routes and plans on a disposable PostgreSQL fixture."""
from __future__ import annotations

import math
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, make_url, select, text, update
from sqlalchemy.orm import sessionmaker


API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT / "src"))
TASK_COUNT = 2_000
SESSION_COUNT = 1_200


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+psycopg" or parsed.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("Benchmark requires the loopback-only disposable PostgreSQL harness.")
    if parsed.username != "postgres" or parsed.database != "orin_benchmark":
        raise SystemExit("Benchmark database must be the dedicated orin_benchmark container database.")
    return url


def _alembic_upgrade() -> None:
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                   cwd=API_ROOT, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _p95(values: list[float]) -> float:
    return sorted(values)[max(0, math.ceil(0.95 * len(values)) - 1)]


def _measure(client: TestClient, method: str, path: str, count: int) -> list[float]:
    samples: list[float] = []
    for _ in range(count):
        started = time.perf_counter()
        response = client.request(method, path)
        samples.append((time.perf_counter() - started) * 1000)
        if response.status_code not in {200, 201}:
            raise RuntimeError(f"{method} {path} returned {response.status_code}")
    return samples


def _report(label: str, samples: list[float]) -> None:
    print(f"PASS {label}: n={len(samples)} p50_ms={median(samples):.2f} "
          f"p95_ms={_p95(samples):.2f} max_ms={max(samples):.2f}")


def main() -> None:
    database_url = _database_url()
    _alembic_upgrade()

    from orin_api.auth import get_current_user
    from orin_api.database import get_session
    from orin_api.focus_domain import local_day_key
    from orin_api.main import app
    from orin_api.models import (
        DailyPlan,
        DailyPlanTask,
        EnergyLevel,
        FocusSession,
        FocusState,
        Task,
        TaskPriority,
        TaskStatus,
        User,
    )

    engine = create_engine(database_url, pool_pre_ping=True)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    owner_id = uuid.uuid4()
    user = User(id=owner_id, email=None, password_hash=None,
                display_name="Synthetic focus benchmark")
    tasks = [
        Task(id=uuid.uuid4(), owner_id=owner_id, title=f"Synthetic benchmark task {i:04d}",
             status=TaskStatus.TODO, priority=TaskPriority.NORMAL, focus_state=FocusState.LATER,
             first_step="Open a document", why="Benchmark fixture", energy_level=EnergyLevel.MEDIUM,
             estimated_minutes=10, is_anchor=False)
        for i in range(TASK_COUNT)
    ]
    try:
        with sessions.begin() as session:
            session.add(user)
            session.flush()
            session.add_all(tasks)
            session.flush()
            session.add_all([
                FocusSession(user_id=owner_id, task_id=tasks[(i + 3) % TASK_COUNT].id,
                             objective="Synthetic history", duration_minutes=25,
                             status="active" if i == 0 else "completed")
                for i in range(SESSION_COUNT)
            ])

        with engine.begin() as connection:
            connection.execute(text("ANALYZE"))
            explain_queries = {
                "today_candidates": text("""
                    EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                    SELECT id FROM tasks WHERE owner_id=:owner
                      AND status IN ('todo','in_progress','blocked')
                      AND focus_state IN ('inbox','later')
                """),
                "active_session": text("""
                    EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                    SELECT fs.id FROM focus_sessions fs JOIN tasks t ON t.id=fs.task_id
                    WHERE fs.user_id=:owner AND fs.status='active' AND t.owner_id=:owner
                      AND t.status NOT IN ('done','cancelled')
                    ORDER BY fs.started_at DESC LIMIT 1
                """),
            }
            for label, statement in explain_queries.items():
                plan = connection.execute(statement, {"owner": owner_id}).scalar_one()[0]["Plan"]
                def plan_nodes(node: dict[str, object]) -> list[dict[str, object]]:
                    nested = node.get("Plans", [])
                    children = [child for child in nested if isinstance(child, dict)] if isinstance(nested, list) else []
                    return [node, *(item for child in children for item in plan_nodes(child))]

                access_path = ",".join(
                    f"{node['Node Type']}:{node.get('Index Name', 'no-index')}"
                    for node in plan_nodes(plan)
                )
                print(f"PLAN {label}: node={plan['Node Type']}, "
                      f"path={access_path}, "
                      f"rows={plan.get('Actual Rows', 0)}, "
                      f"execution_ms={plan.get('Actual Total Time', 0):.3f}, "
                      f"shared_reads={plan.get('Shared Read Blocks', 0)}")

        def override_session():
            with sessions() as session:
                yield session

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_current_user] = lambda: user
        with TestClient(app) as client:
            energy = client.put("/api/v1/focus/energy", json={"energy_level": "medium"})
            if energy.status_code != 200:
                raise RuntimeError(f"energy setup returned {energy.status_code}")

            proposal_samples: list[float] = []
            for index in range(12):
                if index:
                    today = local_day_key(datetime.now(timezone.utc), "UTC")
                    with sessions.begin() as session:
                        plan = session.scalar(select(DailyPlan).where(
                            DailyPlan.user_id == owner_id, DailyPlan.day_key == today))
                        if plan is None:
                            raise RuntimeError("Today's plan disappeared during benchmark reset")
                        session.execute(delete(DailyPlanTask).where(DailyPlanTask.plan_id == plan.id))
                        session.execute(update(Task).where(Task.owner_id == owner_id).values(
                            focus_state=FocusState.LATER, is_anchor=False,
                            today_day_key=None, today_position=None))
                started = time.perf_counter()
                response = client.post("/api/v1/focus/today/propose")
                proposal_samples.append((time.perf_counter() - started) * 1000)
                if response.status_code != 200 or len(response.json().get("tasks", [])) != 3:
                    raise RuntimeError("Today's Three did not return three eligible synthetic tasks")

            _report("Today's Three proposal (2,000 eligible tasks)", proposal_samples)
            _report("Now route", _measure(client, "GET", "/api/v1/focus/now", 45))
            _report("Today route", _measure(client, "GET", "/api/v1/focus/today", 45))
            capture_samples = _measure(client, "POST", "/api/v1/focus/capture", 25)
            _report("Capture save", capture_samples)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


if __name__ == "__main__":
    main()
