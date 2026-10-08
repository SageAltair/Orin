# Architecture overview

Orin begins as a modular monolith. `apps/api` owns the HTTP boundary, domain modules, and PostgreSQL access. `apps/web` is a separately built React client. `apps/worker` is an independently runnable process boundary with no queue or execution behavior yet. Shared public TypeScript response shapes live in `packages/contracts`; tiny framework independent utilities may live in `packages/shared`.

The API health liveness route has no infrastructure dependency. Readiness checks the configured database connection. Persistence uses SQLAlchemy 2 and all schema changes must be added as Alembic revisions.
# Approval policy (Phase 9)

Action risk, required permission, parameter schema, and the `requires_approval` protection are defined only in the server action registry. Autonomy settings cannot change this metadata. An action marked `requires_approval` (the code-level `ALWAYS_REQUIRE_APPROVAL` protection) and every `restricted`/legacy `critical` action always require user approval.

| Mode | Registered LOW | Registered MEDIUM | Registered HIGH / RESTRICTED |
| --- | --- | --- | --- |
| Conservative | Automatic unless protected | Approval | Approval |
| Balanced | Automatic unless protected | Automatic unless protected | Approval |
| Automatic | Automatic unless protected | Automatic unless protected | Approval |
| Custom | Per-action rule (default approval) | Per-action rule (default approval) | Per-action rule (default approval), except protected actions always require approval |

Approvals bind the validated action name and exact validated JSON parameters, are user-owned, and expire after 24 hours. A final execution requires a one-time pending approval decision. The API exposes pending and historical requests under `/api/v1/approvals`; the web Settings page includes autonomy controls and approval review/history.

# Worker security boundary

Authenticated users register devices in Settings. The API returns a high entropy worker credential once and stores only its SHA 256 hash. Devices start pending and become active on authenticated heartbeat; the settings view derives offline status when heartbeats are stale. Revocation disables new claims, cancels unclaimed jobs, and still permits a previously claimed job to report its final state. The Windows worker uses `ORIN_API_URL`, `ORIN_DEVICE_ID`, and `ORIN_WORKER_TOKEN`; it requires HTTPS except on localhost, retries transient network failures, and stops polling after rejected credentials.

Every current worker job requires approval. The API validates one of five fixed capabilities and its parameters, stores server-owned scopes and an expiry, and exposes the request for approval. Only then can a device claim it. The API signs the canonical payload with the device credential; the worker independently validates the HMAC, device ID, expiry, approval reference, and required scope. A durable local SQLite ledger rejects duplicate job IDs. The API accepts authenticated progress and structured results. File access needs explicit `ORIN_ALLOWED_ROOTS`; none are enabled by default. Credential and system locations are blocked, file operations cap content at 1 MB, and process execution is limited to fixed `git_status` and `git_version` argument vectors with `shell=False`.

Jobs expire after 24 hours and remain assigned to the registered device. Claims use row locks and are one-time; a revoked device cannot claim jobs. If a worker disconnects after performing a local side effect but before reporting the result, the API cannot know whether it completed. The local ledger prevents replay after restart, and the UI shows the job as unfinished until expiry instead of silently rerunning it.
