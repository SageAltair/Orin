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

## Production template and proxy trust

The separate `docker-compose.production.yml` builds static assets, runs API services as UID 10001, omits source bind mounts/reload, and exposes the web proxy only on host loopback. The template reserves the private 172.30.0.0/24 subnet and trusts forwarded client addresses only from that network. If that subnet conflicts with your infrastructure, change both its IPAM range and Uvicorn's forwarded allow list together. Nginx replaces incoming X-Forwarded-For with its observed client address. A host TLS terminator must use a reviewed real-IP configuration to preserve individual clients without trusting public spoofed headers. Keep the API and database ports private.

The included Nginx auth limiter protects expensive unauthenticated endpoints and serves same-origin browser/API requests. Configure APP_ENV=production, a private DATABASE_URL, AUTH_SECRET_KEY, HTTPS CORS_ORIGINS/WEB_APP_URL and secure refresh cookies. Use a secret manager or a protected environment file. Do not commit the environment file. Preexisting Docker attachment volumes may need their ownership migrated to UID 10001 before upgrading; inspect/backup them first.

## Background maintenance and worker enrollment

Set BACKGROUND_WORKER_ENABLED=true on the API. It reconciles interrupted extraction, expired device jobs and calendar reminders. Watch API process health and background-maintenance error counts. Reminder delivery is in-app and durable; external push/email channels are not configured.

The local Compose worker is an optional profile. Its enrollment URL must be HTTPS outside localhost; use the gateway's HTTPS URL when enrolling a container worker. Do not expose a Docker socket to the public API. Project test execution is only enabled on a separately provisioned Linux worker host with a prebuilt ORIN_WORKER_EXECUTION_IMAGE containing the required test dependencies. A sanitized read-only source snapshot is supplied to the isolated container; tests must write temporary outputs to /tmp and cannot update live files or access the network. Windows workers support the bounded file/system capabilities without this command runner.

## Data portability and lifecycle

The authenticated `/api/v1/privacy/export` endpoint returns an account ZIP with source records, related versions/links and available attachment bytes. Internal credentials/session tokens are omitted. Password-confirmed account deletion cascades owned relational data and removes attachment bytes. Database/volume backups can retain historical data until their configured retention expires; define and disclose that policy for your deployment. Regularly verify restore procedures in an isolated environment.
