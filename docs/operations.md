# Operations and recovery

## Database changes

Before applying a schema migration to a persistent environment, create and verify a PostgreSQL backup using the deployment's approved backup system. Run migrations once per release with `docker compose -f docker-compose.production.yml run --rm migrate`; API containers wait for that job and never migrate independently. Review offline SQL with `cd apps/api` and `python -m alembic upgrade head --sql` before production changes. Do not use `docker compose down -v` as a backup or recovery procedure: it deletes the local database volume.

Set `BACKUP_DIRECTORY` to an absolute path backed by encrypted off-host storage. `sh scripts/backup-production.sh` briefly pauses the API to create a consistent custom PostgreSQL archive and attachment snapshot with checksums; schedule that short write outage appropriately. Run `sh scripts/verify-backup.sh <snapshot>` after every copy and `sh scripts/restore-drill.sh <snapshot>` on an isolated host on a schedule. Alert when the newest successful backup or restore drill exceeds the deployment's RPO/RTO. `BACKUP_RETENTION_DAYS` documents the deployment policy; enforce deletion in the external backup system so an application compromise cannot erase retained backups. Never run a restore drill against the active database.

Before release, record the current application image and database revision. Roll back application images only when the prior release supports the migrated schema. Otherwise, stop writes and restore the pre-migration database and attachment snapshot together. Never improvise an Alembic downgrade on production data; rehearse each supported downgrade on disposable PostgreSQL and confirm that no irreversible data transformation occurred.

## Health and diagnostics

`GET /health/live` reports that the API process is responding. `GET /health/ready` verifies database connectivity and returns no internal exception details. The private `GET /health/metrics` endpoint exposes bounded request/status/latency and background-maintenance failure counters in Prometheus format; the public Nginx proxy intentionally does not route it. Scrape it only from the private service network. API logs carry a request ID, route template, response status, and duration; AI provider logs include provider/model latency and retry metadata. Logs intentionally omit request bodies. Deployments should route logs to a restricted store, define retention and alerts, and avoid adding prompt or credential fields to log formatters. At minimum, alert on sustained 5xx responses, readiness failure, background-maintenance failures, database saturation, attachment capacity, container restarts, backup age, restore-drill age and TLS certificate expiry. Test alert delivery before launch.

## Private attachments

Attachment bytes are stored under `ATTACHMENT_STORAGE_PATH` (default `data/attachments`) while owner-scoped metadata and extracted text live in PostgreSQL. Back up the storage directory together with the database so file metadata and bytes can be restored consistently. The local Compose stack mounts a named `orin_attachments` volume; `docker compose down -v` removes that volume too. Uploads are limited to five files per request, 10 MB each by default (20 MB total per request), and text extraction is bounded. Configure a private persistent volume or an equivalent access-controlled storage service in deployments; never expose this directory through a public web server.

## Production boundaries

`docker-compose.yml` is a local development stack (including API reload and an idle Worker), not a production deployment. Production startup requires an explicit `DATABASE_URL`, `AUTH_SECRET_KEY`, HTTPS `CORS_ORIGINS` and `WEB_APP_URL`, and `AUTH_REFRESH_COOKIE_SECURE=true`; the API rejects development database/web/CORS defaults and insecure refresh-cookie settings in production mode. Production also requires a TLS terminator, secure secret injection, database backups, edge rate limits for unauthenticated login and registration, and monitoring/retention configuration. GitHub OAuth secrets and encryption keys must be provisioned through the deployment secret manager.

## Production template and proxy trust

The separate `docker-compose.production.yml` builds static assets, runs API services as UID 10001, omits source bind mounts/reload, and exposes the web proxy only on host loopback. The template reserves the private 172.30.0.0/24 subnet and trusts forwarded client addresses only from that network. If that subnet conflicts with your infrastructure, change both its IPAM range and Uvicorn's forwarded allow list together. Nginx replaces incoming X-Forwarded-For with its observed client address. Use `infrastructure/nginx/host-tls.example.conf` as the host proxy contract after replacing its domain and certificate paths. It overwrites `X-Forwarded-For`; the inner proxy accepts that value only from the fixed `172.30.0.1` Compose gateway before replacing the header sent to the API. If the subnet or gateway changes, update Compose, `set_real_ip_from`, and Uvicorn's forwarded allow list together. Test certificate renewal, rejection of a public spoofed forwarding header, and distinct rate-limit identities for distinct clients. Keep the API and database ports private.

The included Nginx auth limiter protects expensive unauthenticated endpoints and serves same-origin browser/API requests. Configure APP_ENV=production, a private DATABASE_URL, AUTH_SECRET_KEY, HTTPS CORS_ORIGINS/WEB_APP_URL and secure refresh cookies. Use a secret manager or a protected environment file. Do not commit the environment file. Preexisting Docker attachment volumes may need their ownership migrated to UID 10001 before upgrading; inspect/backup them first.

## Background maintenance and worker enrollment

Set BACKGROUND_WORKER_ENABLED=true on the API. It reconciles interrupted extraction, expired device jobs and calendar reminders. Watch API process health and background-maintenance error counts. Reminder delivery is in-app and durable; external push/email channels are not configured.

The local Compose worker is an optional profile. Its enrollment URL must be HTTPS outside localhost; use the gateway's HTTPS URL when enrolling a container worker. Do not expose a Docker socket to the public API. Project test execution is only enabled on a separately provisioned Linux worker host with a prebuilt ORIN_WORKER_EXECUTION_IMAGE containing the required test dependencies. A sanitized read-only source snapshot is supplied to the isolated container; tests must write temporary outputs to /tmp and cannot update live files or access the network. Windows workers support the bounded file/system capabilities without this command runner.

## Data portability and lifecycle

The authenticated `/api/v1/privacy/export` endpoint returns an account ZIP with source records, related versions/links and available attachment bytes. Internal credentials/session tokens are omitted. Password-confirmed account deletion cascades owned relational data and removes attachment bytes. Database/volume backups can retain historical data until their configured retention expires; define and disclose that policy for your deployment. Publish the applicable privacy notice and `docs/ai-privacy.md` disclosure before accepting public accounts. Regularly verify restore procedures in an isolated environment.


## Release gate

Require the `verify`, `production-containers`, and `security` GitHub Actions jobs on the protected release branch. The security job audits locked Python and production npm dependencies, scans repository configuration and secrets, scans production images for high/critical fixed vulnerabilities, and publishes an SPDX SBOM. Review and pin base images to registry digests in the release manifest. Block release on any failed required job, an overdue restore drill, expired certificate, failed alert-delivery test, or missing rollback record.


## Read-only local Docker source verification

Before using a running local Orin stack, check that its web and API bind mounts
actually point to the canonical checkout. A healthy HTTP response alone does
not prove that the live containers use the latest source.

From the canonical repository root:

```powershell
python scripts/verify_local_runtime.py
```

If the running API uses an existing local environment file different from this
checkout's `.env`, pass that file explicitly without copying or printing its
contents:

```powershell
python scripts/verify_local_runtime.py --env-file 'C:\path\to\active\.env'
```

The guard checks live source mounts, environment-key drift (never values),
migration-at-startup hazards, and web lockfile freshness. It is **read-only**.
Do not recreate the API with different credentials or a migration-running
command. Use `docker-compose.local-recovery.yml` for any authorized local
API recreation, inspect worker jobs first, and preserve existing volumes.
