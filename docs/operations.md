# Operations and recovery

## Database changes

Before applying a schema migration to a persistent environment, create and verify a PostgreSQL backup using the deployment's approved backup system. Run migrations with `cd apps/api` and `python -m alembic upgrade head`; review offline SQL with `python -m alembic upgrade head --sql` before production changes. Do not use `docker compose down -v` as a backup or recovery procedure: it deletes the local database volume.

For a logical backup, use PostgreSQL's custom archive format, store it outside the database host, encrypt it at rest, and apply a retention policy that matches the deployment's recovery objectives. Periodically restore a copy into an isolated database and verify Alembic state and application readiness before relying on the backup. Do not test restore commands against the active database. This repository does not provision a backup destination, schedule, retention policy, or alerting; operators must configure those for each deployment.

## Health and diagnostics

`GET /health/live` reports that the API process is responding. `GET /health/ready` verifies database connectivity and returns no internal exception details. API logs carry a request ID, route template, response status, and duration; AI provider logs include provider/model latency and retry metadata. Logs intentionally omit request bodies. Deployments should route logs to a restricted store, define retention and alerts, and avoid adding prompt or credential fields to log formatters.

## Private attachments

Attachment bytes are stored under `ATTACHMENT_STORAGE_PATH` (default `data/attachments`) while owner-scoped metadata and extracted text live in PostgreSQL. Back up the storage directory together with the database so file metadata and bytes can be restored consistently. The local Compose stack mounts a named `orin_attachments` volume; `docker compose down -v` removes that volume too. Uploads are limited to five files per request, 10 MB each by default (20 MB total per request), and text extraction is bounded. Configure a private persistent volume or an equivalent access-controlled storage service in deployments; never expose this directory through a public web server.

## Production boundaries

`docker-compose.yml` is a local development stack (including API reload and an idle Worker), not a production deployment. Production startup requires an explicit `DATABASE_URL`, `AUTH_SECRET_KEY`, HTTPS `CORS_ORIGINS` and `WEB_APP_URL`, and `AUTH_REFRESH_COOKIE_SECURE=true`; the API rejects development database/web/CORS defaults and insecure refresh-cookie settings in production mode. Production also requires a TLS terminator, secure secret injection, database backups, edge rate limits for unauthenticated login and registration, and monitoring/retention configuration. GitHub OAuth secrets and encryption keys must be provisioned through the deployment secret manager.
