# Orin API

The API uses PostgreSQL through SQLAlchemy 2. The default development URL targets a local PostgreSQL server. When running under Docker Compose, `DATABASE_URL` is supplied by the root `.env` and should use the `db` hostname.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:DATABASE_URL = "postgresql+psycopg://orin:change-me-locally@localhost:5432/orin"
alembic upgrade head
uvicorn orin_api.main:app --reload
```

Use a local database and credentials that match your environment. Keep passwords in environment variables or an ignored `.env` file. Run `pytest` for API checks.
