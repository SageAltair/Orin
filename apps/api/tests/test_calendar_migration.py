import importlib.util
from pathlib import Path
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_calendar_migration_adds_capability_and_rolls_back_cleanly() -> None:
    migration_path = Path(__file__).parents[1] / "migrations" / "versions" / "20261013_calendar_foundation.py"
    spec = importlib.util.spec_from_file_location("calendar_foundation_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite+pysqlite:///:memory:")
    user_id = uuid.uuid4().hex
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE projects (id CHAR(32) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE capabilities (id CHAR(32) PRIMARY KEY, code VARCHAR(60) UNIQUE, name VARCHAR(100), description VARCHAR(240), is_enabled BOOLEAN)"))
        connection.execute(text("CREATE TABLE user_capabilities (id CHAR(32) PRIMARY KEY, user_id CHAR(32), capability_id CHAR(32), granted BOOLEAN, visible BOOLEAN, pinned BOOLEAN, created_at DATETIME, updated_at DATETIME, UNIQUE(user_id, capability_id))"))
        connection.execute(text("INSERT INTO users (id) VALUES (:id)"), {"id": user_id})
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert "calendar_events" in inspect(connection).get_table_names()
        calendar_capability = connection.execute(text("SELECT id FROM capabilities WHERE code = 'calendar'")).scalar_one()
        assignment = connection.execute(text("SELECT user_id, granted, visible FROM user_capabilities WHERE capability_id = :id"), {"id": calendar_capability}).one()
        assert assignment.user_id == user_id
        assert assignment.granted and assignment.visible
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert "calendar_events" not in inspect(connection).get_table_names()
        assert connection.execute(text("SELECT count(*) FROM capabilities WHERE code = 'calendar'")).scalar_one() == 0
    engine.dispose()


def test_task_scheduling_migration_adds_optional_task_blocks() -> None:
    migration_path = Path(__file__).parents[1] / "migrations" / "versions" / "20261014_task_scheduling.py"
    spec = importlib.util.spec_from_file_location("task_scheduling_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE tasks (id CHAR(32) PRIMARY KEY)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        inspector = inspect(connection)
        assert "task_schedules" in inspector.get_table_names()
        assert {"user_id", "task_id", "start_at", "end_at", "estimated_minutes", "timezone"} <= {
            column["name"] for column in inspector.get_columns("task_schedules")
        }
        assert "ix_task_schedules_user_start" in {index["name"] for index in inspector.get_indexes("task_schedules")}
        assert any(constraint["name"] == "uq_task_schedules_task" for constraint in inspector.get_unique_constraints("task_schedules"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert "task_schedules" not in inspect(connection).get_table_names()
    engine.dispose()


def test_calendar_reminder_migration_preserves_existing_events_and_rolls_back() -> None:
    migration_path = Path(__file__).parents[1] / "migrations" / "versions" / "20261015_calendar_ai_reminders.py"
    spec = importlib.util.spec_from_file_location("calendar_reminders_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE calendar_events (id CHAR(32) PRIMARY KEY, title VARCHAR(240) NOT NULL)"))
        connection.execute(text("INSERT INTO calendar_events (id, title) VALUES ('existing', 'Keep this event')"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert "reminder_minutes" in {column["name"] for column in inspect(connection).get_columns("calendar_events")}
        assert connection.execute(text("SELECT title, reminder_minutes FROM calendar_events WHERE id = 'existing'")).one() == ("Keep this event", None)
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert "reminder_minutes" not in {column["name"] for column in inspect(connection).get_columns("calendar_events")}
        assert connection.execute(text("SELECT title FROM calendar_events WHERE id = 'existing'")).scalar_one() == "Keep this event"
    engine.dispose()
