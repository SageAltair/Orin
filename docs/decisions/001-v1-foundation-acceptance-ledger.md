# Package #179 foundation acceptance ledger

Scope: draft PR #192 only. This is evidence tracking, not approval to close #179.

## Exact-head verification
- [CI run 42287375633](https://github.com/SageAltair/Orin/actions/runs/42287375633) succeeded at commit `2373412d6e73bdad085a52bf22c25e6b015aa75f`.
- The verify workflow creates a disposable `orin_contract_test_ci` PostgreSQL database, runs migration upgrade/rollback/re-upgrade and durable-record preservation checks, and drops that database. This does not test production data.
- Backend/worker suites, Alembic checks, web/mobile checks, and isolated browser acceptance are included in the successful workflow. Passing a suite does not prove every specific contract assertion.

- [CI run 42337985190](https://github.com/SageAltair/Orin/actions/runs/42337985190) completed successfully at `fd1f015d11b7780004f403c928cc753693e324a2`, verifying the database cleanup-marker correction. The remaining behavioral gates are not implied by this result.

## Closure gates
| Gate | Status | Evidence |
| --- | --- | --- |
| Disposable PostgreSQL migration and preservation | PASS | Exact-head Verify 43307156899; disposable DB only |
| Versioned OpenAPI request/response baseline | PASS | Critical-operation manifest + full canonical SHA-256 lock; candidate/reference/security tests and fail-closed digest gate in Verify 43307156899 |
| Authentication, refresh/revoke, cross-owner denial | PASS | Exact-head backend regression suite in Verify 43307156899 |
| Task CRUD, persistence, pagination, worker integration | PASS | Exact-head API/backend and isolated browser/worker jobs in Verify 43307156899 |
| UTC, Dar es Salaam, DST gap/fold scheduling | PASS | Exact-head API/worker tests and isolated Dar timezone job in Verify 43307156899 |
| Reminder lease expiry, rotation, heartbeat and fail-closed | PASS in automated CI | Exact-head API/worker/browser tests and Windows smoke 43307156889; physical visible toast remains deferred #184 |
| ADR-001 accepted with evidence | PASS | Accepted after exact-head Verify 43307156899 and Windows smoke 43307156889 |
| Physical Windows/Android checks | DEFERRED #184 | Explicitly scoped; no native-device pass claimed |

## Required next actions
1. Keep PR #192 draft until the final ADR/ledger acceptance commit passes exact-head Verify and Windows smoke.
2. Review the final diff and current main/base relationship; merge PR #192 with a merge commit only when GitHub reports it mergeable and the exact-head checks pass.
3. Verify post-merge main CI and confirm the authoritative OpenAPI digest/migration contract files are present on main.
4. Close #179 with the merged PR, exact-head CI and post-merge evidence. Only then may #180 begin.
5. Keep physical Windows/Android checks and residual moderate mobile advisories tracked in #184/#21; #179 closure is not public-launch clearance.
No production deployment, device/background-service installation, public publication, paid ads, or real-user data mutation.

## 2026-11-07 exact-head checkpoint (commit `39785b351bb01530dc259609fe9912a71f1422a6`)
- [Verify Orin run 42400995719](https://github.com/SageAltair/Orin/actions/runs/42400995719): **PASS**, exact PR head; includes the corrected isolated Writing browser acceptance test.
- [Windows reminder smoke run 42400995582](https://github.com/SageAltair/Orin/actions/runs/42400995582): **PASS**, exact PR head; this is automated smoke coverage, **not** physical Windows toast visibility evidence.
- Previous isolated browser failure is no longer reproduced by the exact-head Verify Orin workflow. The change clears a previously applied Writing search filter before persistence assertions. No claim of general document persistence correctness beyond the tested scenario.
- **Still incomplete:** checked-in versioned full OpenAPI compatibility baseline, explicit evidence mapping for refresh/revoke and cross-owner denial, complete task pagination/worker integration and reminder lease protocol coverage, and ADR-001 acceptance. Do not merge/close solely on green workflows.
- **Release boundary:** package #179 stays open; PR #192 stays draft; physical device checks remain deferred to #184. No production or user-data operation is authorized by these results.

## 2026-11-07 security-schema regression checkpoint
- Previous exact head `f8115e399cb13e169d67f4472d8f81ad88c0aa40`: [Verify Orin 42405905343](https://github.com/SageAltair/Orin/actions/runs/42405905343) **PASS** and [Windows reminder smoke 42405905349](https://github.com/SageAltair/Orin/actions/runs/42405905349) **PASS**.
- New `test_v1_openapi_security_integrity.py` validates all OpenAPI security scheme references, scope declaration types, and absence of anonymous alternatives on release-critical task/notification/reminder endpoints.
- The new test is **UNVERIFIED** until exact-head CI completes. This is structural API security metadata verification, **not** proof of refresh/revoke, owner isolation, or runtime permission enforcement.
- Keep #179 open and PR #192 draft until every closure gate is met. No downstream package or native-device work authorized.

## 2026-11-08 exact-head and branch recovery checkpoint
- [Verify Orin 42420130285](https://github.com/SageAltair/Orin/actions/runs/42420130285): **PASS** at `f748a23fa3735ce5d58eeeecf2618f6088b2e346`.
- [Windows reminder smoke 42420130303](https://github.com/SageAltair/Orin/actions/runs/42420130303): **PASS** at the same exact head. Physical-device verification remains deferred to #184.
- PR #192 metadata confirms its head branch is `docs/179-v1-contract-freeze-decision`, still open/draft, and issue #179 remains open. The earlier branch-resolution failure requires a fresh write check, not an assumption that repository access is permanently lost.
- **Still required:** canonical versioned OpenAPI compatibility baseline, explicit runtime authorization/ownership and task/worker/reminder protocol evidence, and recorded ADR-001 acceptance. Passing CI alone is not authorization to merge or advance.

## 2026-11-08 closure-focused evidence reconciliation

This checkpoint replaces the repeated test-invention loop with direct mapping of existing assertions to package #179's closure criteria. Evidence is source-level plus exact-head CI; it is not a claim of manual device acceptance.

**Verified head:** `d5e1757fbc5458b153f334760caf2d1694383a31`.
- [Verify Orin 42450513045](https://github.com/SageAltair/Orin/actions/runs/42450513045): PASS on that head.
- [Windows reminder smoke 42450513136](https://github.com/SageAltair/Orin/actions/runs/42450513136): PASS on that head.

| Required acceptance | Existing executable evidence | Assessment |
| --- | --- | --- |
| Disposable PostgreSQL upgrade/rollback/preservation | `apps/api/tests/test_v1_postgres_migration_acceptance.py`, `test_v1_migration_contract.py`; disposable PostgreSQL in `.github/workflows/verify.yml` | PASS in isolated CI; not production recovery |
| Auth refresh/revoke and ownership denial | `apps/api/tests/test_auth.py::test_access_token_requires_auth_and_refresh_rotation_detects_reuse`, `test_logout_revokes_current_access_and_refresh_tokens`, `test_user_cannot_list_or_modify_another_users_data`, `test_v1_foreign_workspace_header_cannot_write_or_read_tasks` | PASS in exact-head suite |
| Task CRUD/persistence and pagination | `apps/api/tests/test_priority_tasks.py::test_v1_task_lifecycle_persists_across_requests_and_is_owner_scoped`, `test_priority_inventory_pagination_and_validation`; `apps/api/tests/test_auth.py::test_authenticated_workspace_task_lifecycle_survives_token_refresh` | PASS in isolated suite |
| Timezone and DST boundaries | `apps/api/tests/test_v1_calendar_timezone_contract.py`, `apps/api/tests/test_calendar.py`; `apps/worker/tests/test_windows_reminders.py::test_v1_reminder_dst_fold_preserves_distinct_utc_deadlines`, `test_v1_reminder_spring_forward_uses_real_elapsed_time` | PASS in exact-head suite |
| Worker paging and fail-closed notification | `apps/worker/tests/test_windows_reminders.py::test_pagination_reads_all_and_no_partial_snapshot`, `test_browser_workspace_lease_fails_closed_before_native_toast`, `test_missing_local_browser_heartbeat_suppresses_and_retries_due_toast`, `test_foreground_auth_revocation_clears_pending_even_without_stop_signal` | PASS in exact-head suite |
| API schema integrity | `apps/api/tests/test_v1_api_contract.py`, `test_v1_openapi_integrity.py`, `test_v1_openapi_reference_integrity.py`, `test_v1_openapi_security_integrity.py`, `test_v1_route_shadowing.py` | PASS structural checks; **INCOMPLETE canonical checked-in compatibility baseline** |
| ADR-001 contract freeze | `docs/decisions/001-v1-foundation-contract-freeze.md` | PROPOSED; **approval/acceptance still required** |
| Native physical Windows/Android delivery | Explicitly assigned to #184 | DEFERRED, not PASS |

**Remaining closure work (bounded):**
1. Generate and check in a deterministic v1 OpenAPI compatibility baseline, and make CI compare generated v1 operations/request-response shapes against that baseline with documented additive-change policy.
2. Review/accept ADR-001 and link this evidence. No unapproved breaking contract change.
3. Re-run exact-head CI, verify PR diff and merge safety, merge #192, verify main, and close #179 with linked evidence. Only then start #180.

**No further duplicate sentinel tests** unless a specific untested failure is demonstrated. This is an evidence reconciliation, not a claim that #179 is finished.


## 2026-11-12 full OpenAPI contract freeze checkpoint

- Reviewed the generated candidate from [Verify Orin run 43290879119](https://github.com/SageAltair/Orin/actions/runs/43290879119), generated at PR #192 head `297a0ed3de9e7b51d125b8fde8a2342ce2606265`.
- Candidate inventory: **166 versioned paths, 217 operations, 217 unique operation IDs, 319 local references, zero unresolved references**, and two HTTP bearer schemes (`BearerAuth`, `WorkerBearerAuth`).
- Effective-security inventory found exactly four anonymous operations, all intentional: register, login, refresh, and GitHub OAuth callback. Worker heartbeat, claim, and event operations use `WorkerBearerAuth`. No undefined or malformed security declarations.
- Canonical full-schema SHA-256: `bb4693d1fb7f27efb06ca7f6010f620db093b9ebdbbbfedf2db2735d1bbe1816`. The lock is checked in at `apps/api/contracts/v1-openapi.sha256`; CI regenerates the review candidate, validates its structure, then compares the complete canonical v1 schema digest. The candidate and security inventory remain CI artifacts for inspection.
- The digest lock avoids committing a generated 441 KB JSON file while still failing closed on any path, field, requiredness, response, or security drift. Updating it requires an explicit reviewed `--write` operation.
- [Prior exact-head Verify Orin run 43290879119](https://github.com/SageAltair/Orin/actions/runs/43290879119): application, PostgreSQL migration, browser acceptance, web, Android, production-container, and security steps completed successfully; the final fail-closed baseline check failed because the digest baseline had not yet been added at that commit. [Windows reminder smoke](https://github.com/SageAltair/Orin/actions/runs/43290879009) passed at that head.
- Added regression coverage for JSON Pointer array indices and the exact set of intentionally public API operations. Added a SHA-256 regression test proving schema changes alter the lock digest.
- Current PR head: `05361f08997ea72a574ad4d60064193b9b0eecbf`. Exact-head CI for this commit is pending; no PASS is claimed yet. ADR-001 remains proposed pending that verification and final review. Package #179 remains open; no downstream package is authorized.


## 2026-11-12 exact-head CI correction

- [Verify Orin run 43304102605](https://github.com/SageAltair/Orin/actions/runs/43304102605) reached the full backend/worker collection and failed before executing that suite because the newly appended public-operation regression test contained a literal `\\n` source line (Python `SyntaxError`, line 105). The failure was introduced by the test edit, not by the API or migration implementation.
- Corrected the source line and aligned the compatibility test/ADR wording with the complete OpenAPI SHA-256 lock in commit `f4296ff2ac8c2774dcb2049c84af14724be88f94`.
- The prior run's Android, web, production-container, isolated worker, knowledge, workspace-scope, pagination and Dar timezone jobs passed. Windows reminder smoke passed at the same prior head. The full verify job is **not PASS** because of the test-collection error.
- Final exact-head CI after the correction is required before ADR-001 can be accepted or PR #192 can be merged.


## 2026-11-12 exact-head verification and platform contract reconciliation

- Current verified PR head before this documentation reconciliation: `22987a706dd4772bdec5f4c0843d697da7cfba6d`.
- [Verify Orin run 43304895267](https://github.com/SageAltair/Orin/actions/runs/43304895267): **PASS**, all 12 jobs succeeded at that exact head, including disposable PostgreSQL migration upgrade/rollback/re-upgrade and preservation, backend/worker regressions, web and Android checks, browser acceptance (Writing/reminders, worker, knowledge, workspace scope, pagination, Dar timezone), production-container smoke, security, OpenAPI candidate/reference/security checks, and the fail-closed SHA-256 baseline comparison.
- [Windows reminder smoke run 43304895260](https://github.com/SageAltair/Orin/actions/runs/43304895260): **PASS** at the same exact head. It verifies installer/shortcut identity in a disposable profile; it does **not** verify human-visible toast delivery on a physical device.
- The OpenAPI candidate is 166 versioned paths / 217 operations / 217 unique operation IDs / 319 local references, with zero unresolved references, two bearer schemes, and only four intentional public operations. The complete canonical schema digest is locked at `apps/api/contracts/v1-openapi.sha256` as `bb4693d1fb7f27efb06ca7f6010f620db093b9ebdbbbfedf2db2735d1bbe1816`; the candidate is retained as a CI artifact rather than a 441 KB generated JSON file.
- The registration HTTP 429 failure is resolved without weakening the production five-per-peer-per-minute registration limit: each signup-heavy browser scenario now gets its own disposable API/database process, and a backend test protects the 5-success / 6th-429 behavior plus forwarded-header spoof resistance.
- PostgreSQL service logs include the expected unique-key conflicts exercised by `test_workspace_race.py`; the test proves concurrent first-workspace creation converges on one Personal workspace. Both parameterized cases passed. These are handled savepoint conflicts, not unhandled test failures.
- The prior architecture overview incorrectly said there was no mobile app, no reminder delivery, and no API peer rate limiting. This PR now reconciles those statements with the current Android client, opt-in local reminder limitations, Windows foreground companion, and API-enforced peer limits. The current documentation commit requires its own exact-head CI before ADR acceptance/merge.
- Physical Windows toast visibility and Android device delivery remain **DEFERRED #184**, as required by the revised sequence. No native-device PASS is claimed.

**Current package status:** API/DB/auth/worker/notification contract implementation and CI are verified at the preceding head. ADR-001 remains proposed until the platform documentation correction is verified at the new exact head and the decision is recorded. Keep #179 open and do not begin #180.


## 2026-11-12 final #179 acceptance

**All #179 acceptance criteria are met in isolated CI.** Exact current implementation/platform-documentation head `8534370e4aba642b3f5a5c0447c50c01f4353439` passed [Verify Orin 43307156899](https://github.com/SageAltair/Orin/actions/runs/43307156899) (**12/12 jobs success**) and [Windows reminder smoke 43307156889](https://github.com/SageAltair/Orin/actions/runs/43307156889) (**success**). The main verify job completed every step, including backend/worker regressions, PostgreSQL migration acceptance and cleanup, schema upgrade/offline preview, frontend and Android checks, browser workflows, and the final fail-closed OpenAPI SHA-256 comparison.

### Final evidence summary
- **API:** 166 paths, 217 operations, 217 unique operation IDs, 319 local references, zero unresolved references, two bearer schemes, four intended public operations; canonical digest `bb4693d1fb7f27efb06ca7f6010f620db093b9ebdbbbfedf2db2735d1bbe1816`.
- **Database:** frozen Alembic lineage sentinel and disposable PostgreSQL upgrade/rollback/re-upgrade with representative data preservation; only the CI-created database was disposed.
- **Identity/auth:** refresh rotation/revocation, owner/workspace denial, worker bearer scheme and negative credential checks passed.
- **Tasks/time:** lifecycle/persistence, pagination, timezone and DST fold/gap coverage passed.
- **Notifications:** browser lease, heartbeat, fail-closed, Windows queue tests and Windows identity smoke passed. Human-visible Windows toast and physical Android delivery remain deferred to #184.
- **Registration:** test suite now isolates signup-heavy browser scenarios; production five-per-peer-per-minute limit remains unchanged and spoofed forwarding headers do not bypass it.
- **Documentation:** architecture overview and ADR now describe actual web/Android/Windows support and notification limits.

### Dependency and residual-risk reconciliation
- The code dependencies from #48/#21 are integrated from merged work including PR #146; the #149 engineering correction is merged in PR #178.
- Historical issues #21/#48 remain open because their broader acceptance still includes physical device gates and residual mobile dependency risk. #129 (visible Windows toast) and #130 (physical Android local reminders) remain **BLOCKED pending explicit owner consent/observation** and are assigned to #184 by this package's acceptance scope. No device was installed or modified.
- The security workflow passed its zero-critical/zero-high policy, but **11 moderate mobile build-tool advisories remain** tracked in #21. This package does not claim they are resolved; their risk disposition remains required before public launch.

**ADR-001 is accepted by release engineering. #179 is ready for PR merge, post-merge main verification, and issue closure. #180 remains untouched until that closure.**