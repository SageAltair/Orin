# ADR-001: Orin v1 foundation contract freeze (proposed)

Status: **Proposed for Package #179**. This document is a change-control decision and contract inventory, **not** evidence that contracts or migrations have passed verification. Approval/acceptance occurs only when #179's executable contract tests and migration evidence are linked.

Date: 2026-11-06
Scope: public v1 API, PostgreSQL schema evolution, authentication/session lifecycle, browser-to-Windows reminder protocol.

## Decision

1. **HTTP boundary.** `/api/v1` is the supported API namespace. FastAPI's generated OpenAPI document is the schema source of truth. Changes to existing request/response fields, status codes, authentication requirements, idempotency semantics or workspace scoping are compatibility changes requiring an explicit review. Additive optional fields are preferred. Do not rename endpoints or silently reinterpret existing fields.
2. **Persistence.** PostgreSQL and SQLAlchemy 2 own durable state. All schema changes require an ordered Alembic revision. No production downgrade or destructive migration is authorized by this ADR. For each revision, demonstrate upgrade from the previous supported revision, preservation of representative task/auth/notification data, and either a tested downgrade on disposable data or a documented forward-recovery/restore procedure where downgrade is unsafe.
3. **Identity.** Access-token authentication and revocable refresh sessions are separate from workspace authorization. An authenticated owner does not gain access to another owner's tasks, notifications, leases, or worker jobs. Device credentials are independently revocable. Avoid storing raw access/refresh/worker tokens in logs or local reminder queues.
4. **Notification protocol.** Windows reminders remain explicit foreground opt-in, tied to a current authenticated browser session, workspace ID, generation-scoped short-lived lease, fresh browser heartbeat and local loopback stop. Missing/expired/mismatched lease, disconnected browser, auth rejection, or unavailable suppression policy fails closed. A generic toast API success is **not** proof of human-visible scheduled delivery. No silent auto-start, background service, or Android installation.
5. **Time.** Persist unambiguous instants with offsets/UTC and apply the user's selected IANA timezone for presentation and local scheduling. Acceptance must include Africa/Dar_es_Salaam and DST-observing zones, including invalid/ambiguous local times.
6. **Release scope.** Package #179 freezes these boundaries before #180–#190. Native physical acceptance belongs to #184, but #179 must document the native boundary and pass its isolated contract tests. No later package begins until #179 is closed with evidence.

## Change-control gate

For a proposed breaking change: (a) enumerate affected API routes, database revisions, clients, workers, and existing user data; (b) publish an impact/rollback plan; (c) add backward/forward compatibility tests; (d) obtain explicit recorded approval before merging; (e) link exact-head CI and the approved exception on #179 or the active later package. The absence of a test or approval is **BLOCKED**, never implied acceptance.

## Required executable evidence before accepting this ADR

| Contract | Required evidence | Status |
| --- | --- | --- |
| API request/response and status behavior | Checked-in OpenAPI baseline and compatibility regression | Pending |
| Database migration graph | Alembic single-head check, disposable PostgreSQL upgrade and data preservation | Pending |
| Recovery | Disposable downgrade or forward-recovery/restore drill with data assertions | Pending |
| Auth/session and workspace ownership | Cross-owner negative tests, refresh/revoke tests | Pending |
| Task lifecycle and timezone | CRUD, pagination, timezone, due-reminder integration tests | Pending |
| Windows browser/worker lease | Rotation, expiry, revocation, heartbeat and fail-closed tests | Pending |
| Exact-head verification | Green CI linked to #179 | Pending |

Existing test suites and previous CI runs may contribute evidence only when their exact commits, assertions, and applicability are recorded. This document does not substitute for that evidence.

## References

- [Package #179](https://github.com/SageAltair/Orin/issues/179)
- [Architecture overview](../architecture.md)
- [Windows reminder security and opt-in](../../apps/worker/WINDOWS_REMINDERS.md)
- [Alembic migrations](../../apps/api/migrations/versions)
