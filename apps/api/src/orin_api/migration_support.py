"""Helpers for keeping Alembic's own schema compatible with long revisions."""

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, MetaData, String, Table, inspect
from sqlalchemy.engine import Connection


ALEMBIC_VERSION_LENGTH = 128


def ensure_alembic_version_column_length(connection: Connection) -> None:
    """Create or widen Alembic's version table before it records a revision."""
    inspector = inspect(connection)
    if not inspector.has_table("alembic_version"):
        Table(
            "alembic_version",
            MetaData(),
            Column("version_num", String(ALEMBIC_VERSION_LENGTH), primary_key=True),
        ).create(connection)
        return

    columns = {column["name"]: column for column in inspector.get_columns("alembic_version")}
    version_column = columns.get("version_num")
    if version_column is None:
        raise RuntimeError("alembic_version is missing its version_num column")

    current_length = getattr(version_column["type"], "length", None)
    if current_length is not None and current_length >= ALEMBIC_VERSION_LENGTH:
        return

    operations = Operations(MigrationContext.configure(connection))
    with operations.batch_alter_table("alembic_version") as batch:
        batch.alter_column(
            "version_num",
            type_=String(ALEMBIC_VERSION_LENGTH),
            existing_type=version_column["type"],
            existing_nullable=False,
        )


# Alembic's public version-table hook keeps offline SQL consistent with online setup.
from alembic.ddl.postgresql import PostgresqlImpl


class WideVersionPostgresqlImpl(PostgresqlImpl):
    __dialect__ = "postgresql"

    def version_table_impl(self, **kwargs):
        table = super().version_table_impl(**kwargs)
        table.c.version_num.type = String(ALEMBIC_VERSION_LENGTH)
        return table
