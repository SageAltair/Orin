# Package #179 foundation acceptance ledger

Scope: draft PR #192 only. This is evidence tracking, not approval to close #179.

## Exact-head verification
- [CI run 42287375633](https://github.com/SageAltair/Orin/actions/runs/42287375633) succeeded at commit `2373412d6e73bdad085a52bf22c25e6b015aa75f`.
- The verify workflow creates a disposable `orin_contract_test_ci` PostgreSQL database, runs migration upgrade/rollback/re-upgrade and durable-record preservation checks, and drops that database. This does not test production data.
- Backend/worker suites, Alembic checks, web/mobile checks, and isolated browser acceptance are included in the successful workflow. Passing a suite does not prove every specific contract assertion.

- [CI run 42337985190](https://github.com/SageAltair/Orin/actions/runs/42337985190) completed successfully at `fd1f015d11b7780004f403c928cc753693e324a2`, verifying the database cleanup-marker correction. The remaining behavioral gates are not implied by this result.

## Closure gates
| Gate | Status | Next evidence |
| --- | --- | --- |
| Disposable PostgreSQL migration and preservation | PASS | CI run above |
| Versioned OpenAPI request/response baseline | INCOMPLETE | Complete compatibility snapshot and regression |
| Authentication, refresh/revoke, cross-owner denial | INCOMPLETE | Link exact negative assertions |
| Task CRUD, persistence, pagination, worker integration | INCOMPLETE | Link or implement explicit isolated assertions |
| UTC, Dar es Salaam, DST gap/fold scheduling | INCOMPLETE | Link or implement timezone assertions |
| Reminder lease expiry, rotation, heartbeat and fail-closed | INCOMPLETE | Link or implement protocol assertions |
| ADR-001 accepted with evidence | INCOMPLETE | Record decision after tests |
| Physical Windows/Android checks | DEFERRED #184 | Document boundary, do not claim native PASS |

## Required next actions
Map existing assertions to each incomplete gate; implement missing tests instead of assuming generic CI success. Re-run exact-head CI, review compatibility and migration impacts, merge safely, verify main, then close #179 with evidence. Do not begin #180 before closure. Do not deploy, install services, or touch real user data.
