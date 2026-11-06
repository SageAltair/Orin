"""Opt-in PostgreSQL upgrade/rollback acceptance for Package #179.

Run only against a NEW, EMPTY, disposable database named orin_contract_test_*.
Example: ORIN_V1_MIGRATION_TEST_DATABASE_URL=postgresql+psycopg://.../orin_contract_test_ci pytest -q tests/test_v1_postgres_migration_acceptance.py
Never point this at a user, development, staging, or production database.
"""
import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

API_ROOT = Path(__file__).resolve().parents[1]
HEAD = "20261106_browser_reminder_lease"
PARENT = "20261105_priority_guidance"
ENV_KEY = "ORIN_V1_MIGRATION_TEST_DATABASE_URL"


def _disposable_url():
    raw = os.getenv(ENV_KEY)
    if not raw:
        pytest.skip(f"{ENV_KEY} not set: disposable PostgreSQL required")
    parsed = urlsplit(raw)
    db_name = parsed.path.lstrip("/")
    if not parsed.scheme.startswith("postgresql") or not db_name.startswith("orin_contract_test_"):
        pytest.fail("Refusing migration acceptance outside a named disposable PostgreSQL database")
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("Migration acceptance requires local PostgreSQL; no remote database access")
    return raw


def test_v1_postgres_upgrade_rollback_and_preservation(monkeypatch):
    url = _disposable_url()
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        # Hard stop before Alembic mutates anything. Never reuse a populated DB.
        with engine.connect() as conn:
            existing = inspect(conn).get_table_names()
            assert not existing, f"Disposable database must be empty, found: {existing}"

        # env.py obtains its URL through application settings, not alembic.ini.
        monkeypatch.setenv("DATABASE_URL", url)
        from orin_api.config import get_settings
        get_settings.cache_clear()
        cfg = Config(str(API_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(API_ROOT / "migrations"))

        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == HEAD
            assert "browser_reminder_leases" in inspect(conn).get_table_names()
            # An unrelated durable marker detects accidental broad data deletion.
            conn.execute(text("CREATE TABLE contract_preservation_probe (id integer PRIMARY KEY, payload text NOT NULL)"))
            conn.execute(text("INSERT INTO contract_preservation_probe VALUES (1, 'must-survive')"))

        command.downgrade(cfg, "-1")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == PARENT
            assert "browser_reminder_leases" not in inspect(conn).get_table_names()
            assert conn.execute(text("SELECT payload FROM contract_preservation_probe WHERE id=1")).scalar_one() == "must-survive"

        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == HEAD
            assert "browser_reminder_leases" in inspect(conn).get_table_names()
            assert conn.execute(text("SELECT payload FROM contract_preservation_probe WHERE id=1")).scalar_one() == "must-survive"
    finally:
        engine.dispose()
        # No drop: caller owns disposal of this dedicated test database.
