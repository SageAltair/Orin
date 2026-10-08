# Orin API

The API uses PostgreSQL through SQLAlchemy 2. The default development URL targets a local PostgreSQL server. When running under Docker Compose, `DATABASE_URL` is supplied by the root `.env` and should use the `db` hostname.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:DATABASE_URL = "postgresql+psycopg://orin:change-me-locally@localhost:5432/orin"
$env:AUTH_SECRET_KEY = (openssl rand -hex 32)
alembic upgrade head
uvicorn orin_api.main:app --reload
```

Use a local database and credentials that match your environment. Keep passwords in environment variables or an ignored `.env` file. Run `pytest` for API checks.

## Core API

Alembic creates the relational core and seeds the five initial capabilities. Apply schema changes with `alembic upgrade head`.

- `GET|PUT /api/v1/users/me/preferences`
- `GET /api/v1/capabilities`
- `GET|POST /api/v1/projects`
- `PATCH /api/v1/projects/{project_id}`
- `GET|POST /api/v1/tasks`
- `PATCH /api/v1/tasks/{task_id}`
- `GET /api/v1/activity`

Core endpoints derive the user scope from the authenticated principal. Preference responses include visible, hidden, and pinned capability codes. Project and task create/update operations write corresponding activity entries.

## Authentication

Configure `AUTH_SECRET_KEY` with a unique 32-byte random value encoded as 64 hex characters. The setting has no development fallback; authentication routes return unavailable until it is set, and production configuration fails startup if it is missing. `AUTH_REFRESH_COOKIE_SECURE` defaults to `true`; set it to `false` only for local HTTP development. Access tokens last 15 minutes by default, while refresh sessions have a 30-day absolute lifetime.

- `POST /api/v1/auth/register` — creates an email/password account.
- `POST /api/v1/auth/login` — returns a short-lived bearer access token and sets an HttpOnly refresh cookie.
- `POST /api/v1/auth/refresh` — rotates the refresh cookie and returns a new access token.
- `POST /api/v1/auth/logout` — revokes the current session and clears the refresh cookie.
- `GET /api/v1/auth/me` — returns the authenticated user.

The refresh token is opaque and stored as a SHA-256 digest. Reuse of a rotated token revokes its session family. Protected core endpoints derive ownership from the bearer token; caller-supplied user IDs are no longer accepted as identity. Email/password accounts use Argon2id password hashes. Validation responses omit submitted values so credentials are not reflected in error bodies.

The core `users` table predates credentials. The auth migration preserves existing user rows with null email/password pairs; only registered accounts with credentials can authenticate. Existing accounts need an explicit account-provisioning or recovery flow before they can log in.
