# Architecture overview

Orin begins as a modular monolith. `apps/api` owns the HTTP boundary, domain modules, and PostgreSQL access. `apps/web` is a separately built React client. `apps/worker` is an independently runnable authenticated process boundary. Shared public TypeScript response shapes live in `packages/contracts`; tiny framework independent utilities may live in `packages/shared`.

The API health liveness route has no infrastructure dependency. Readiness checks the configured database connection. Persistence uses SQLAlchemy 2 and all schema changes must be added as Alembic revisions.

# Execution targets and mobile API

Worker jobs persist a requested target (`local`, `cloud`, or `auto`) separately from the selected target. The deterministic selector checks authorization, health/availability, required capabilities, available resources, data privacy/residency, explicit preference, and any supplied cost/latency limits. Unknown cost or latency cannot satisfy a user-specified limit. `auto` prefers an eligible local Worker and will not move private data to cloud. No cloud environment is currently provisioned, so cloud requests return a recoverable unavailable decision and no cloud execution is claimed. Target selection is a provider-neutral seam for a future provisioned Worker.

The versioned `/api/v1` API uses bearer access tokens with refresh sessions that can be revoked. `POST /api/v1/commands` accepts an optional `Idempotency-Key` header; retries for the same user and same command return the cached result, while reusing a key for different text returns `409`. Command submission is limited to 20 requests per authenticated user per minute in shared database storage. `GET /api/v1/commands/{id}` is owner-scoped for status polling. The API OpenAPI document is available from FastAPI and remains the current contract source; there is no mobile app or push notification delivery implementation. Login and registration still rely on deployment edge rate limiting for IP-based abuse protection.

API responses carry a validated or generated `X-Request-ID`; request logs include that ID, the route template, status, and duration without logging request bodies or query strings. AI provider success and retry logs include provider/model, attempt, status, and latency. Activity correlation uses stable command, approval, worker-job, or integration-connection IDs. Metrics aggregation, retention, and alerting are deployment responsibilities and are not configured in this repository.
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

Every current worker job requires approval. The API validates one of five fixed capabilities and its parameters, stores server-owned scopes and an expiry, and exposes the request for approval. AI intents can propose a fixed worker capability through the action registry; the server selects the user's single recently connected device, validates the proposal, and holds it for approval. Only then can a device claim it. The API signs the canonical payload with the device credential; the worker independently validates the HMAC, device ID, expiry, approval reference, and required scope. A durable local SQLite ledger rejects duplicate job IDs. The API accepts authenticated progress and structured results. File access needs explicit `ORIN_ALLOWED_ROOTS`; none are enabled by default. Credential and system locations are blocked, file operations cap content at 1 MB, and process execution is limited to fixed `git_status`, `git_version`, `python_tests`, and `npm_tests` argument vectors with `shell=False`, a fixed working directory, filtered environment, and a timeout.

Jobs expire after 24 hours and remain assigned to the registered device. Claims use row locks and are one-time; a revoked device cannot claim jobs. If a worker disconnects after performing a local side effect but before reporting the result, the API cannot know whether it completed. The local ledger prevents replay after restart, and the UI shows the job as unfinished until expiry instead of silently rerunning it.

# Project intelligence, memory, personalization, and focus

Project context is assembled by `ProjectContextService` for one explicitly mentioned, user-owned project. It includes a bounded list of project metadata, tasks, blockers, recent activity, and up to five relevant structured memories. The AI receives that compact context as reference data; it cannot use context text as instructions or change project state without a supported action.

Structured memories are user-owned, optionally project-scoped records with a type, title, content, source, confidence, and archive state. Users can search, edit, archive, restore, and delete them. Secret-like key/value content is rejected. Explicit environment preferences are stored separately and synchronized with existing capability visibility and pin settings so hidden navigation remains recoverable. Focus sessions persist on the API, use server-derived expiry, allow pause/resume/complete/cancel, and enforce one active session per user. Project overview progress uses actual task counts; file and agent panels remain empty until those integrations exist.
