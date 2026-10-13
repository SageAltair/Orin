from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, text


def test_batch_activity_downgrade_maps_rows_to_legacy_type() -> None:
    migration_path = Path(__file__).parents[1] / "migrations" / "versions" / "20261010_task_batch_activity.py"
    spec = importlib.util.spec_from_file_location("task_batch_activity_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE activity (activity_type VARCHAR(40) NOT NULL)"))
        connection.execute(text("INSERT INTO activity (activity_type) VALUES ('tasks_created_batch'), ('task_created')"))
        migration.downgrade_batch_activity_types(connection)
        actual = connection.execute(text("SELECT activity_type FROM activity ORDER BY activity_type")).scalars().all()
        assert actual == ["task_created", "task_created"]
    engine.dispose()
