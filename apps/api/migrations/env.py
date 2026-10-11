from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from orin_api.config import get_settings
from orin_api.database import Base
from orin_api.migration_support import ensure_alembic_version_column_length
import orin_api.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", str(get_settings().database_url).replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=str(get_settings().database_url), target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.begin() as connection:
        # Alembic normally creates this table as VARCHAR(32). Prepare it first,
        # otherwise a long revision ID fails while Alembic records the upgrade.
        ensure_alembic_version_column_length(connection)
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
