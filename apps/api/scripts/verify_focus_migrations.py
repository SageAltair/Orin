"""Exercise focus migration upgrade/downgrade cycles on a disposable PostgreSQL DB."""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text


API_ROOT = Path(__file__).resolve().parents[1]
BASELINE = "20261009_activity"
LEGACY_TASKS = [
    ("todo", "later", None),
    ("in_progress", "active", None),
    ("blocked", "later", None),
    ("done", None, "completed"),
    ("cancelled", "released", "released"),
]
OWNER_ID = uuid.UUID("7f33d2a0-f210-4b43-a54b-88d2f921dd83")
TASK_IDS = [uuid.UUID(f"7f33d2a0-f210-4b43-a54b-88d2f921dd{i:02x}") for i in range(1, 6)]


def alembic(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=API_ROOT, check=True)


def seed_legacy_rows() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO users (id, display_name, email, password_hash) VALUES (:id, :name, NULL, NULL)"),
            {"id": OWNER_ID, "name": "Migration check"},
        )
        for task_id, (legacy_status, _focus_state, _timestamp) in zip(TASK_IDS, LEGACY_TASKS, strict=True):
            connection.execute(
                text("INSERT INTO tasks (id, owner_id, title, status, priority) VALUES (:id, :owner, :title, :status, 'normal')"),
                {"id": task_id, "owner": OWNER_ID, "title": f"Legacy task {legacy_status}", "status": legacy_status},
            )
    engine.dispose()


def verify_focus_mapping() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT id, title, status::text, focus_state::text, completed_at, released_at "
                 "FROM tasks WHERE owner_id = :owner ORDER BY id"), {"owner": OWNER_ID},
        ).all()
        assert len(rows) == len(LEGACY_TASKS), f"Expected five migrated rows; found {len(rows)}"
        for row, (legacy_status, focus_state, timestamp_kind) in zip(rows, LEGACY_TASKS, strict=True):
            _task_id, title, status, state, completed_at, released_at = row
            assert title == f"Legacy task {legacy_status}", (title, legacy_status)
            assert status == legacy_status, (status, legacy_status)
            assert state == focus_state, (state, focus_state)
            assert (completed_at is not None) == (timestamp_kind == "completed"), title
            assert (released_at is not None) == (timestamp_kind == "released"), title
    engine.dispose()


def verify_legacy_rows() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT title, status::text FROM tasks WHERE owner_id = :owner ORDER BY id"), {"owner": OWNER_ID},
        ).all()
        expected = [(f"Legacy task {status}", status) for status, _, _ in LEGACY_TASKS]
        assert rows == expected, f"Legacy tasks changed during downgrade: {rows!r}"
    engine.dispose()


def main() -> None:
    if not os.environ.get("DATABASE_URL", "").startswith("postgresql+"):
        raise SystemExit("Set DATABASE_URL to the disposable PostgreSQL instance first.")
    alembic("upgrade", BASELINE)
    seed_legacy_rows()
    for cycle in range(1, 3):
        alembic("upgrade", "head")
        verify_focus_mapping()
        print(f"PASS PostgreSQL upgrade cycle {cycle}: five legacy task mappings and timestamps")
        alembic("downgrade", BASELINE)
        verify_legacy_rows()
        print(f"PASS PostgreSQL downgrade cycle {cycle}: task titles and legacy statuses preserved")
    alembic("downgrade", "base")
    print("PASS PostgreSQL full-chain downgrade to base")


if __name__ == "__main__":
    main()
