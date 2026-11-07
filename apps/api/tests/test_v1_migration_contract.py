"""Package #179: executable baseline for the frozen v1 migration lineage.

Changes to the head revision require an explicit ADR impact/compatibility
review. This is a structural guard, not a substitute for PostgreSQL
upgrade/downgrade and data-preservation acceptance.
"""
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


API_ROOT = Path(__file__).resolve().parents[1]
FROZEN_V1_HEAD = "20261106_browser_reminder_lease"


def _script_directory() -> ScriptDirectory:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "migrations"))
    return ScriptDirectory.from_config(config)


def test_v1_migration_head_is_explicitly_frozen() -> None:
    script = _script_directory()
    assert script.get_heads() == [FROZEN_V1_HEAD], (
        "The v1 migration contract changed. Record an approved ADR, "
        "compatibility/migration evidence, and update this baseline deliberately."
    )


def test_v1_migration_graph_is_connected_and_reversible_in_structure() -> None:
    script = _script_directory()
    revisions = list(script.walk_revisions())
    assert revisions, "The migration history must not be empty"
    assert len({revision.revision for revision in revisions}) == len(revisions)
    assert sum(revision.is_base for revision in revisions) == 1
    assert revisions[0].revision == FROZEN_V1_HEAD
    assert all(callable(revision.module.upgrade) for revision in revisions)
    assert all(callable(revision.module.downgrade) for revision in revisions)
