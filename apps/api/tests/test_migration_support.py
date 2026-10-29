from sqlalchemy import create_engine, inspect, text

from orin_api.migration_support import (
    ALEMBIC_VERSION_LENGTH,
    ensure_alembic_version_column_length,
)


def test_fresh_database_gets_wide_alembic_version_table() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        ensure_alembic_version_column_length(connection)
        column = inspect(connection).get_columns("alembic_version")[0]
        assert column["name"] == "version_num"
        assert column["type"].length == ALEMBIC_VERSION_LENGTH
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": "20261017_task_verification_criteria"},
        )
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "20261017_task_verification_criteria"
        )
    engine.dispose()


def test_existing_alembic_version_is_widened_without_losing_revision() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        )
        connection.execute(text("INSERT INTO alembic_version VALUES ('20261016_project_milestones')"))
        ensure_alembic_version_column_length(connection)

        column = inspect(connection).get_columns("alembic_version")[0]
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert column["type"].length == ALEMBIC_VERSION_LENGTH
        assert revision == "20261016_project_milestones"
        connection.execute(
            text("UPDATE alembic_version SET version_num = :revision"),
            {"revision": "20261017_task_verification_criteria"},
        )
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "20261017_task_verification_criteria"
        )
    engine.dispose()
