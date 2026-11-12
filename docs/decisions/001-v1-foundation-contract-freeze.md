# ADR-001: Orin v1 foundation contract freeze

Status: **Accepted by release engineering on 2026-11-12 UTC after exact-head verification; see final acceptance review below**. This is a change-control decision and contract inventory, not proof of release readiness. Acceptance requires the full API digest check, executable contract tests, disposable PostgreSQL migration evidence, and the final CI run linked below.

Date: 2026-11-06
Scope: public v1 API, PostgreSQL schema evolution, authentication/session lifecycle, browser-to-Windows reminder protocol.

## Decision

## Client and platform support

| Surface | v1 support boundary | Verification boundary |
| --- | --- | --- |
| Web | Primary browser workspace; authenticated against the shared `/api/v1` contract. | Browser acceptance runs in isolated CI. |
| Android | Expo/React Native client using the same API, identity and workspace boundaries. Local reminders are explicit opt-in, limited to known/synchronized items, and best-effort; no server push or remote updates while the app is closed. | Automated export/type/test checks run in CI; physical-device acceptance belongs to #184. |
| Windows companion | Optional foreground reminder companion only; explicit opt-in, active browser session, short-lived workspace lease and heartbeat. No service or silent auto-start. | Windows smoke CI verifies identity/installer safety, not human-visible toast delivery; physical-device acceptance belongs to #184. |
| Cloud worker | No cloud execution environment is provisioned; cloud target requests fail recoverably and do not move private data. | Provisioning and operational acceptance are later gated work, not claimed by #179. |

The Android application is a supported client, not an Android background-service installation. The Windows companion is not a required desktop client. No native physical-device pass is claimed in this package.


1. **HTTP boundary.** `/api/v1` is the supported API namespace. FastAPI's generated OpenAPI document is the schema source of truth. The complete canonical v1 document is locked by `apps/api/contracts/v1-openapi.sha256`; CI regenerates a review-only candidate, validates its references and security declarations, then compares the full canonical digest. Changes to existing request/response fields, status codes, authentication requirements, idempotency semantics or workspace scoping are compatibility changes requiring an explicit review. Additive optional fields are preferred. Do not rename endpoints or silently reinterpret existing fields.
2. **Persistence.** PostgreSQL and SQLAlchemy 2 own durable state. All schema changes require an ordered Alembic revision. No production downgrade or destructive migration is authorized by this ADR. For each revision, demonstrate upgrade from the previous supported revision, preservation of representative task/auth/notification data, and either a tested downgrade on disposable data or a documented forward-recovery/restore procedure where downgrade is unsafe.
3. **Identity.** Access-token authentication and revocable refresh sessions are separate from workspace authorization. An authenticated owner does not gain access to another owner's tasks, notifications, leases, or worker jobs. Device credentials are independently revocable. Avoid storing raw access/refresh/worker tokens in logs or local reminder queues.
4. **Notification protocol.** Windows reminders remain explicit foreground opt-in, tied to a current authenticated browser session, workspace ID, generation-scoped short-lived lease, fresh browser heartbeat and local loopback stop. Missing/expired/mismatched lease, disconnected browser, auth rejection, or unavailable suppression policy fails closed. A generic toast API success is **not** proof of human-visible scheduled delivery. The Android client may schedule known local reminders only after explicit opt-in; this is best-effort and is not server push or guaranteed background delivery. No silent auto-start or background-service installation.
5. **Time.** Persist unambiguous instants with offsets/UTC and apply the user's selected IANA timezone for presentation and local scheduling. Acceptance must include Africa/Dar_es_Salaam and DST-observing zones, including invalid/ambiguous local times.
6. **Release scope.** Package #179 freezes these boundaries before #180–#190. Native physical acceptance belongs to #184, but #179 must document the native boundary and pass its isolated contract tests. No later package begins until #179 is closed with evidence.

## Change-control gate

For a proposed breaking change: (a) enumerate affected API routes, database revisions, clients, workers, and existing user data; (b) publish an impact/rollback plan; (c) add backward/forward compatibility tests; (d) obtain explicit recorded approval before merging; (e) link exact-head CI and the approved exception on #179 or the active later package. The absence of a test or approval is **BLOCKED**, never implied acceptance.

## Recorded executable evidence for this ADR

| Contract | Required evidence | Status |
| --- | --- | --- |
| API request/response and status behavior | `apps/api/contracts/v1-critical-operations.json`, `apps/api/contracts/v1-openapi.sha256`, `test_v1_checked_in_compatibility.py`, OpenAPI candidate/reference/security tests | Full canonical v1 field-level schema locked by SHA-256; candidate/reference/security checks and digest gate PASS in exact-head CI 43307156899 |
| Database migration graph | `test_v1_migration_contract.py`, `test_v1_postgres_migration_acceptance.py`, isolated CI PostgreSQL | PASS in exact-head CI 43307156899 |
| Recovery | Disposable PostgreSQL upgrade/rollback/re-upgrade and preservation in CI | Verified in disposable environment only |
| Auth/session and workspace ownership | `test_auth.py` refresh rotation, logout revocation, foreign workspace denial | Verified by exact-head CI |
| Task lifecycle and timezone | `test_priority_tasks.py`, `test_v1_calendar_timezone_contract.py`, worker DST tests | Verified by exact-head CI |
| Windows browser/worker lease | `test_windows_reminders.py` browser lease, heartbeat, auth revocation, fail-closed tests | Verified in isolated smoke CI; native visual delivery deferred #184 |
| Exact-head verification | [Verify Orin 43307156899](https://github.com/SageAltair/Orin/actions/runs/43307156899) and [Windows reminder smoke 43307156889](https://github.com/SageAltair/Orin/actions/runs/43307156889), both at PR head `8534370e4aba642b3f5a5c0447c50c01f4353439` | **PASS**: all 12 Verify jobs and the Windows smoke job succeeded. The final fail-closed OpenAPI SHA-256 baseline check passed. |

Existing test suites and previous CI runs may contribute evidence only when their exact commits, assertions, and applicability are recorded. This document does not substitute for that evidence.

## References

- [Package #179](https://github.com/SageAltair/Orin/issues/179)
- [Architecture overview](../architecture.md)
- [Windows reminder security and opt-in](../../apps/worker/WINDOWS_REMINDERS.md)
- [Alembic migrations](../../apps/api/migrations/versions)

## 2026-11-08 historical acceptance review (superseded by final acceptance below)

The exact-head security retry completed successfully at `e0941fff82527abe6c6eb17b8286833a0e8413ee`; the SBOM download failure was transient. No security check was waived. The API baseline protects selected critical operations, but not all v1 request/response field-level types, defaults, nullability or enum semantics. **ADR-001 remains proposed**, pending completion of that contract freeze and recorded acceptance. CI passing is not itself architecture approval. Do not merge or close #179 until these gates are satisfied. No native-device verification is claimed.


## 2026-11-12 final acceptance review

**ADR-001 ACCEPTED for the Orin v1 foundation contract freeze.** Exact-head [Verify Orin run 43307156899](https://github.com/SageAltair/Orin/actions/runs/43307156899) and [Windows reminder smoke run 43307156889](https://github.com/SageAltair/Orin/actions/runs/43307156889) both completed successfully at `8534370e4aba642b3f5a5c0447c50c01f4353439`. Verify passed all 12 jobs, including backend/worker regressions, disposable PostgreSQL migration upgrade/rollback/re-upgrade and preservation, web/mobile checks, browser acceptance, production-container smoke, security scanning, candidate validation and the fail-closed OpenAPI digest check.

- Canonical OpenAPI inventory: 166 versioned paths, 217 operations, 217 unique operation IDs, 319 local references, zero unresolved references, two bearer schemes, and four intentionally public operations. The complete canonical digest is `bb4693d1fb7f27efb06ca7f6010f620db093b9ebdbbbfedf2db2735d1bbe1816`.
- The worker bearer contract is additive documentation of the existing runtime credential boundary; worker credential format, hash/revocation checks and permission behavior were retained. The registration 429 correction isolates test scenarios without changing the production five-per-peer-per-minute limit. No breaking-change exception is granted or required by this ADR.
- Platform support and notification limits are now explicit: browser web, Android Expo client with opt-in best-effort local reminders (no server push), Windows foreground companion with browser lease/heartbeat (no service/autostart), and no provisioned cloud execution environment.
- The security workflow passed its existing zero-critical/zero-high policy. **Eleven moderate mobile build-tool advisories remain** tracked under #21; this ADR does not waive or claim remediation of those findings. They remain a release risk to be dispositioned before public launch.
- Physical Windows visible-toast and Android device delivery remain **DEFERRED #184**; no native-device pass is claimed. Related historical issues #21/#48 and device gates #129/#130 remain open until their own acceptance is completed. The engineering fix for #149 is merged in PR #178.
- No production deployment, production migration, device/background-service installation, real-user data mutation, public publication or paid advertising occurred.

This acceptance freezes the current v1 contract baseline. Future breaking changes still require impact analysis, compatibility/migration tests, and explicit recorded approval before merge.
