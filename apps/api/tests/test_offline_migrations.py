from pathlib import Path
import subprocess
import sys


def test_complete_offline_sql_supports_long_revisions():
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=Path(__file__).parents[1], text=True, capture_output=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert "VARCHAR(128)" in result.stdout
    assert "20261024_reliability" in result.stdout
    assert "CREATE TABLE notifications" in result.stdout
