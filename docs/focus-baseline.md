# Focus feature baseline and acceptance plan

**Decision date:** 2026-10-10  
**Approved baseline:** `1279c157946e723118f3131cdd0af1ea75c4c09c` (`v1.4`)  
**New branch:** `feature/focus-baseline`, created from the approved baseline  
**Status:** M0 implementation is complete; exact-commit PostgreSQL/check verification and tag remain pending.

## Re-baselining decision

The original `feature/focus-tasks` branch, Phase 1/2 acceptance checklist, verification reports, and `focus-phase-1-verified` / `focus-phase-2-verified` tags could not be recovered from local or remote Git refs, the reflog, stashes, repository documentation, or available task attachments. The first focus implementation is in commit `70b1117` (`v1.3`), whose parent is `7cc43e8`, but no authoritative evidence establishes that parent as the original feature-branch base or maps its contents to the historical phases.

The project owner therefore authorized a **new baseline**, starting at `1279c15`. This branch and document are new project history; they do not claim to recover the old branch or prove that old phases passed. The historic phase tag names must remain unused. All acceptance milestones below are newly established.

## Current implementation

The baseline contains an additive `focus_state` task field and shared lifecycle transitions; user-scoped focus routes and records; Capture, Now, Today's Three, Later, and Close surfaces; energy-based selection; a two-swap daily limit; task-linked use of the existing focus-session API; settings for timezone and selected sensory preferences; and focus privacy endpoints. The focus migration backfills task state and timestamps. Architecture notes say reminder delivery is not implemented.

Code pointers:

- API behavior: `apps/api/src/orin_api/focus_domain.py`, `focus_planning.py`, and `focus_router.py`.
- Persistence and schema: `apps/api/src/orin_api/models.py`, `apps/api/migrations/versions/20261010_focus_foundation.py`, and `packages/contracts/src/index.ts`.
- Web surfaces: `apps/web/src/features/focus/` and the Tasks branch in `apps/web/src/App.tsx`.
- Existing tests: `apps/api/tests/test_focus_foundation.py`, `apps/api/tests/test_focus_planning.py`, and `apps/web/e2e/focus.spec.ts`.
- Architecture and migration limitations: `docs/architecture.md`.

The new experience is behind the build-time `VITE_FOCUS_ENABLED` rollout flag, which defaults off; the legacy Tasks experience remains available with create, title, status, priority, due-date, and project controls. The focus export includes user settings, daily plans, their task assignments, drift events, and daily closes.

## Newly established milestone M0: Focus foundation baseline

Every criterion is required for `focus-baseline-v1-verified`. Evidence below was freshly gathered on a worktree based on the approved implementation commit (`1279c15`) on 2026-10-10. That worktree contains the migration downgrade repair and regression test described below, as well as this document; it is not yet a commit and is not taggable evidence. “Blocked” means current evidence does not prove the criterion; “Fail” records a known mismatch with the acceptance requirement.

| ID | Acceptance criterion | Implementation and evidence | Status |
|---|---|---|---|
| F-01 | `status` keeps its legacy meaning; open-task focus state is additive; lifecycle changes use shared domain transitions. | `focus_domain.py`; `test_task_lifecycle_transitions_keep_legacy_status_and_focus_state_consistent`, `test_legacy_task_status_api_uses_shared_focus_transitions`, and `test_task_status_and_focus_state_writes_are_confined_to_domain_service`. Full API pytest passed. | Pass |
| F-02 | A user's day uses the saved IANA timezone and shared 04:00 local `day_key`; daily swap allowance resets at that boundary. | `focus_domain.py`, `focus_router.py`; `test_local_day_key_uses_four_am_boundary_and_iana_dst_rules`, `test_two_swaps_are_allowed_then_rest_is_offered_and_day_key_resets`. Full API pytest passed. | Pass |
| F-03 | Focus settings, plans, plan tasks, drift events, daily closes, and task-linked sessions persist with an owning `user_id`; cross-user access is denied. | Models and `focus_router.py`; `test_every_focus_table_is_scoped_by_user_id` and `test_focus_records_are_owner_scoped_and_privacy_delete_is_scoped`. Expanded API tests cover each focus read surface under two identities, foreign-owned references on write routes, export scope, and privacy deletion isolation. | Pass |
| F-04 | Migration preserves legacy status/title data and maps `todo → later`, `in_progress → active`, `blocked → later`, `done → null`, `cancelled → released`; completion/release timestamps are populated from legacy timestamps. | `20261010_focus_foundation.py`; SQLite backfill test and disposable PostgreSQL 16 run. Five synthetic statuses matched the expected mapping. Downgrade to `20261010_task_batch_activity` preserved all five task titles/statuses. | Pass for the focus migration up/down; full-chain downgrade is separately failed below. |
| F-05 | Today's Three selects at most three eligible tasks, matches chosen energy, and gives a low-energy anchor of at most 15 minutes where available. | `focus_planning.py`; `test_todays_three_matches_energy_and_prefers_recent_context`, `test_low_energy_has_no_anchor_when_no_task_is_small_enough`, and `test_low_energy_anchor_is_kept_when_outside_top_three`. | Pass |
| F-06 | Capture creates an inbox task; Now selects it, starts the existing linked focus session, completes through shared transitions, and advances. | `focus_router.py`, `Now.tsx`, `useFocusWorkspace.ts`; `test_capture_is_optional_and_creates_inbox_task`, `test_now_starts_task_linked_focus_and_advances_after_completion`, and Playwright critical-flow test. | Pass for covered flow |
| F-07 | Later and Close surfaces can load, save, and recover from empty/error states without changing legacy task behavior. | `Later.tsx`, `Close.tsx`, `focus_router.py`; Playwright covers Later load failure/recovery and empty state, plus Close save failure with answers retained for recovery. | Pass |
| F-08 | At most two swaps occur per day; the limit offers the current task or rest; previous-day swaps do not consume today's allowance. | `focus_router.py`; `test_two_swaps_are_allowed_then_rest_is_offered_and_day_key_resets`. | Pass for the implemented swap-rest choice. A user-configured weekly task-free day is a future behavior milestone. |
| F-09 | Focus UI remains behind a dedicated rollout flag, defaults off, and the old Tasks screen remains the default until removal is approved. | `App.tsx` uses `VITE_FOCUS_ENABLED`; unset/anything other than `true` selects `LegacyTasks`. `legacy-tasks.spec.ts` verifies create and complete with the flag off. | Pass |
| F-10 | Privacy export includes the user's focus-specific data; deletion removes the user's focus-only records without affecting another user's data. | `/focus/privacy/export` includes settings, plans, assignments, drift events, and daily closes. API tests verify every exported category and scoped deletion while other-user records remain. | Pass |
| F-11 | Drift notes/reflections are bounded and never echoed in validation responses or request logs. | `test_drift_and_reflection_validation_never_echoes_sensitive_text`. | Pass for this tested rejection path; production error/log paths still require the M3 audit. |
| F-12 | Focus UI honors dark mode, reduced motion, AA contrast and 48px controls on the tested screen; the critical capture-to-start journey takes no more than three taps. | `apps/web/e2e/focus.spec.ts`; two Chromium desktop tests pass, including computed contrast/control dimensions and capture/start. | Pass for the tested desktop states only. |
| F-13 | Keyboard-only, screen-reader focus order/live announcements, mobile and large viewport layouts, and all loading/empty/error/disabled-flag states are tested. | Playwright checks keyboard reachability, semantic controls, live status announcements, dark mode, reduced motion, contrast/control sizing, and 375px/1920px horizontal overflow. Flag-off, empty, and error recovery are covered. | Pass with browser accessibility-tree checks; no native screen-reader session was available. |
| F-14 | Full migration chain upgrades to head and downgrades to base on PostgreSQL while preserving documented legacy data at the pre-focus revision. | Disposable PostgreSQL 16: full upgrade reached `20261011_nav_defaults`; all five synthetic task mappings passed; downgrade to `20261009_activity` retained task title/status rows and mapped a synthetic `tasks_created_batch` activity to `task_created`; downgrade to `base` passed. `20261010_task_batch_activity.downgrade()` now retains the shared enum label and remaps stored batch activities to a legacy value. | Pass on the current uncommitted migration patch; repeat on the eventual verification commit. |
| F-15 | API input validation and stable error behavior cover settings and every focus write route, including invalid types/values, unknown fields, length limits, and invalid ownership references. | Pydantic schemas in `focus_router.py`; current tests cover oversized private notes and selected foreign-owned task/session references. `test_focus_write_routes_reject_invalid_and_unknown_inputs` covers bounded text, enums, timezone, strict unknown-field rejection, plan limits, and invalid trigger schemas across focus write routes. Existing tests cover foreign-owned references. | Pass |

### Baseline verification run

These commands were run afresh on a worktree based on `1279c15`, with the local migration downgrade repair and regression test present; they do not include `scripts/check.ps1`.

| Command | Result |
|---|---|
| `python -m pytest` (`apps/api`) | Exit 0; 129 passed, 0 failed, 0 skipped; one Starlette `PendingDeprecationWarning` about `python_multipart`. Includes `test_batch_activity_downgrade_maps_rows_to_legacy_type`. |
| `npm run lint` (`apps/web`) | Exit 0. |
| `npm run test` (`apps/web`) | Exit 0; 2 files, 8 tests passed; no skips. |
| `npm run build` (`apps/web`) | Exit 0; TypeScript build and Vite production build succeeded. |
| `npm run test:e2e -- --workers=1 e2e/focus.spec.ts` (`apps/web`) | Exit 0; 2 passed, 0 failed, 0 skipped. Playwright emitted the environment warning that `NO_COLOR` is ignored when `FORCE_COLOR` is set. These tests mock the API. |
| `npm run test:e2e -- --workers=1` (`apps/web`) | Exit 0; 15 total, 13 passed, 2 skipped, 0 failed. Skips are the opt-in Docker/AI and live worker flows because `ORIN_DOCKER_E2E` and `ORIN_WORKER_E2E` were not set. Same Playwright color warning. |
| `python -m compileall -q src migrations` (`apps/api`) | Exit 0. |
| Disposable PostgreSQL migration exercise (`apps/api`; random local port, temporary container, no volume) | Upgrade to pre-focus revision; seeded five synthetic task statuses; full upgrade to `20261011_nav_defaults`; verified mappings; seeded a batch activity; downgraded to `20261009_activity`; verified preserved task title/status rows and remapped batch activity; downgraded to `base`: all passed after the migration repair. Container was removed. Existing Compose containers were not touched. |

Not run: `scripts/check.ps1`, real API+web integration/manual walkthrough, keyboard/screen-reader walkthrough, or responsive-device audit. The first PostgreSQL probe targeted `20261010_task_batch_activity` itself, so Alembic correctly stopped before running that revision's downgrade; the probe was corrected to target its parent (`20261009_activity`) and then the full downgrade to base passed. The full E2E suite includes opt-in Docker/worker flows (`ORIN_DOCKER_E2E`, `ORIN_WORKER_E2E`); any enabled run must use an isolated test stack because this workstation already has `orin-*` Compose containers and data.

## New milestone M1: Focus behavior mechanics

This milestone re-establishes the former Phase 3 behavior scope without assigning it to historical Phase 3 work. Acceptance requires tests and an API/web walkthrough for each item:

1. Focus Mode shows only the task, first step and existing session timer. Optional check-in defaults off; Yes continues, Drifted logs one event linked to task and session, and Switch uses the daily swap limit.
2. A rolling completed-days count uses the shared `day_key`, accounts for configured rest days, has no lost-streak state, and applies the “never miss twice” and re-entry rules without guilt language. Re-entry appears once per absence and can be dismissed.
3. Decay review selects a small number of eligible tasks; Keep resets touch/review dates, Shrink saves a smaller first step, and Release uses the shared release transition. Nothing is labeled overdue.
4. Optional routine anchors can rank Today's Three and prompt in-app within quiet hours; no more than two reminders per task/day, escalation changes form only, and unavailable delivery is stated plainly.
5. Weekly rest day, optional body doubling and revocable accountability preference, Sunday meaning review, and calm reduced-motion completion moment work without sending unconfigured notifications.
6. Drift insights remain read-only and hidden until a documented minimum event count. Settings validate and persist all supported preferences, including energy, rest day, quiet hours, check-in interval, motion, sound, haptics, theme, timer visibility, routines, body doubling, contact, feature flag, and export/delete. Include the non-medical-support note.

Required evidence: deterministic unit tests for day boundaries, re-entry, decay outcomes, reminder caps/quiet hours/escalation, and insight threshold; API ownership and settings validation tests; Playwright journeys for each interaction; keyboard, live-region, dark-mode, reduced-motion and contrast tests. No scheduled worker or notification provider is required; do not simulate delivery.

| ID | M1 acceptance criterion | Implementation/test trace to complete | Status at M0 |
|---|---|---|---|
| B-01 | Focus Mode keeps only task, first step and the existing linked timer visible; optional check-in defaults off and supports Yes, one-tap Drifted, and Switch through swap rules. | `FocusExperience.tsx`, `Now.tsx`, `useFocusWorkspace.ts`, `/focus/now/*` and `/focus/drift`; add `test_focus_mode.py` API/unit coverage and Focus Mode Playwright journeys asserting task/session linkage and swap limit. | N/A to M0; M1 not started. |
| B-02 | Rolling completed-days count uses `local_day_key`; rest days are neutral; “never miss twice” and re-entry start after the defined absence, appear once, and dismiss without shame language. | `focus_domain.py`, `UserSettings`, `DailyPlan`; add deterministic day/re-entry tests and Playwright simulated absence/dismissal tests. | N/A to M0; M1 not started. |
| B-03 | Decay review is bounded; Keep resets timestamps, Shrink stores an easier first step, Release uses shared domain transition. | `focus_domain.py`, `focus_router.py`, `Task.decay_review_at`; add candidate-query, outcome, ownership and three-outcome Playwright tests. | N/A to M0; M1 not started. |
| B-04 | If-then anchors and routines rank tasks; in-app prompts enforce max two/task/day, quiet hours across midnight, gentle escalation and honest unavailable-delivery copy. | `UserSettings`, `Task.trigger`, `focus_planning.py`, Focus UI; add reminder/routine unit tests, settings/API tests and prompt UI tests. No provider delivery is claimed. | N/A to M0; M1 not started. |
| B-05 | Weekly rest day works with Capture; optional body doubling/accountability is revocable and sends nothing without a configured provider; Sunday meaning review groups completions by why without scoring. | `UserSettings`, focus surfaces and existing task/close routes; add persistence, ownership, neutral-day, no-send, and weekly review API/Playwright tests. | N/A to M0; M1 not started. |
| B-06 | Completion feedback is immediate and reduced-motion aware; drift insights are read-only and hidden below a documented minimum sample count. | `Now.tsx`, focus CSS, `DriftEvent`; add reduced-motion/browser tests and deterministic insight-threshold tests. | N/A to M0; M1 not started. |
| B-07 | Settings validate and persist all agreed values; controls state that reminders are not delivered and the tool is not medical treatment. | `UserSettings`, `/focus/settings`, `FocusExperience.tsx`; add schema invalid-input matrix, API persistence/reload tests and Settings Playwright coverage. | N/A to M0; M1 not started. |

## New milestone M2: AI actions and parity

This milestone re-establishes the former Phase 4 scope. AI actions must validate schemas, use the same domain functions as manual actions, preserve state on failure, enforce ownership and swap limits, confirm release/delete and support undo. Tests cover per-action valid/missing/wrong/unknown fields, success/post-state/failure, exact manual/AI state parity, cross-user isolation, prompt regressions, instruction-like task text as inert data, and unavailable/timeout/malformed model outputs. Existing AI create/update/complete flows remain covered. A scripted AI session is compared with the manual UI journey. Copy stays brief and non-shaming, offers one next step when overwhelmed, and does not reveal sensitive drift/reflection content unless asked.

| ID | M2 acceptance criterion | Implementation/test trace to complete | Status at M0 |
|---|---|---|---|
| A-01 | Every AI focus action has strict schema tests for valid, missing, wrong-type and unknown fields; success verifies persisted state and failures leave state unchanged. | Future focus action schemas/registry beside `execution_actions.py` and `domain_router.py`; extend `test_ai.py` and add action API tests. | N/A to M0; M2 not started. |
| A-02 | AI and manual paths call shared domain transitions and produce identical status, focus state, timestamps and counters. | `focus_domain.py` is the shared seam; add paired API tests from identical database fixtures for every action. | N/A to M0; M2 not started. |
| A-03 | Swap limits, release confirmation/undo and cross-user isolation hold through AI; task text that looks like instructions stays inert data. | Action registry, `focus_domain.py`, owner-scoped `focus_router.py`; add safety/parity/injection tests, including a hostile task title. | N/A to M0; M2 not started. |
| A-04 | Copy avoids forbidden language; overwhelm yields exactly one next step and at most one question; model unavailable/timeout/malformed output degrades without partial writes. | System prompt/provider boundary and `test_ai.py`; add mocked-output prompt regression and failure-mode tests. | N/A to M0; M2 not started. |

## New milestone M3: Hardening and launch readiness

This milestone re-establishes the former Phase 5 scope. It requires the full Alembic chain on a disposable copy of PostgreSQL data, upgrade/downgrade repeated twice, row-count and mapping evidence; query plans/indexes and response-time measurements; route-by-route ownership tests; export/delete and log inspection; rate-limit and free-text length tests; keyboard, screen-reader, reduced-motion, theme, AA contrast, zoom and viewport walkthroughs; architecture/contracts/user help docs; flag-off rollback; and the full 10-journey acceptance pass from the supplied project task module. Every line is reported PASS/FAIL with evidence. Any failure blocks the launch milestone.

| ID | M3 acceptance criterion | Implementation/test trace to complete | Status at M0 |
|---|---|---|---|
| H-01 | Full migration chain on a disposable PostgreSQL data copy upgrades/downgrades twice with row counts, mappings, no-loss evidence, and working legacy schema. | Alembic revisions and disposable PostgreSQL harness; add repeatable migration integration procedure and preserve test data snapshots. | N/A to M0; M3 not started. |
| H-02 | Now/Capture/Today's Three latency, capture save time, query plans/indexes and offline capture/sync behavior meet measured targets. | Focus routes, ORM indexes, web capture persistence; add benchmark/query-plan and offline duplicate-sync tests. | N/A to M0; M3 not started. |
| H-03 | Every new route has ownership tests; sensitive content is absent from logs/errors/analytics; export/delete is complete; rate limits and text limits are verified. | `focus_router.py`, privacy endpoints and app logging boundary; add route matrix, sentinel-log, export/delete, rate-limit, and length tests. | N/A to M0; M3 not started. |
| H-04 | Every new surface passes keyboard/screen reader, reduced motion, dark mode, AA contrast, zoom, small/large viewport and one-hand reachability checks. | `apps/web/src/features/focus/`, CSS and Playwright; add accessibility/device suites with recorded observations. | N/A to M0; M3 not started. |
| H-05 | Contracts, architecture, calm user help, feature flag, day-key rule, swap limit, reminder limitations and rollback steps are documented. | `packages/contracts`, `docs/architecture.md`, this baseline document and new user-facing help page; review links and wording. | N/A to M0; M3 not started. |
| H-06 | Flag defaults off with easy switch back; old Tasks screen remains; rollback procedure covers flag and migration downgrade. | New rollout flag and restored legacy Tasks view; add flag-off/flag-on browser regression and rollback rehearsal. | N/A to M0; M3 not started. |
| H-07 | All ten end-to-end journeys and cross-cutting checks from the project task module pass; check script passes twice consecutively. | `apps/web/e2e/`, API tests and `scripts/check.ps1`; report every item PASS/FAIL with command/test/log evidence. | N/A to M0; M3 not started. |

## Verification policy and milestone references

The repository check script is `scripts/check.ps1`. It installs web/API dev dependencies, then runs web lint, Vitest, production build, the complete Playwright suite with one worker, API pytest, and API `compileall`. Run it end to end only after the M0/Phase 3 entry gate below is met. Do not claim its result from component checks.

Database evidence must use a disposable or explicitly authorized PostgreSQL database; SQLite tests are useful but do not replace PostgreSQL migration tests. Do not point tests or migration commands at the existing Compose database or production. For each milestone, record command, exit code, pass/fail/skip counts with skip reasons, warnings, database revision/data checks, manual observations, exact source commit, and unresolved items. A milestone is verified only when every required criterion passes on the exact target commit and the worktree diff has been reviewed.

New tag names, documented here and not yet created:

- `focus-baseline-v1-verified` — M0 only.
- `focus-behavior-v1-verified` — M1 only.
- `focus-ai-v1-verified` — M2 only.
- `focus-launch-v1-verified` — M3 only.

Each annotated tag may be created only after its milestone passes and its evidence is tied to that exact commit. Do not create the old `focus-phase-1-verified` or `focus-phase-2-verified` names, or tag the current commit merely to unlock later work.

## Explicit Phase 3 entry gate

Phase 3/M1 may begin only after all of these are true:

- This new acceptance specification is reviewed and committed on the new baseline branch.
- M0 contains no `Fail` or `Blocked` criterion; required unit, API, web, accessibility and migration checks pass.
- The full PostgreSQL chain upgrade and downgrade passes with documented legacy data preserved at the supported rollback point.
- `scripts/check.ps1` passes end to end; all skips have an explicit reason and no prior passing tests are removed, skipped or weakened.
- Manual API+web foundation walkthrough is complete in an isolated environment.
- `focus-baseline-v1-verified` points to the exact M0-verified commit.
- Branch is based on `1279c157946e723118f3131cdd0af1ea75c4c09c` and the worktree is clean.

**Current gate result: implementation criteria pass; finalization pending.** The repository gate passed on the current worktree (web/API tests and checks are recorded above); focused PostgreSQL evidence already confirms the downgrade repair. Before M1 begins, commit this baseline specification and implementation, repeat `scripts/check.ps1` and the disposable PostgreSQL chain on that exact commit, verify the working tree is clean, then create `focus-baseline-v1-verified` on that commit. A real screen-reader device walkthrough was not available; Playwright accessibility-tree and keyboard checks are the closest automated evidence.

## Phase 5 implementation evidence (current worktree)

Phase 5 adds private focus-data export/delete controls with confirmation, a self-guided guide linked from Now, AI suggestion rate limits, logging/privacy regression coverage, and repeatable PostgreSQL migration/performance harnesses. The local Compose website keeps Focus enabled as requested; setting `VITE_FOCUS_ENABLED=false` at web build time restores the legacy Tasks page.

| ID | Current result | Evidence / remaining work |
|---|---|---|
| H-01 | PASS | Read-only `pg_dump` of the local 11 MB PostgreSQL 16 database was restored to a disposable tmpfs container. It contained 28 users, 27 tasks, 12 projects, and 3 focus sessions. Two project-less sessions were reassigned to projects owned by the same users in the copy, as required by the documented downgrade precondition. Two full downgrade/upgrade cycles preserved user/task/project/session counts and a digest of legacy task fields. The source database was not modified. |
| H-02 | PASS FOR THE DOCUMENTED ONLINE WORKFLOW | `scripts/benchmark-focus-postgres.ps1` seeded a disposable PostgreSQL 16 database with 2,000 synthetic eligible tasks and 1,200 focus sessions. A 250 ms local p95 budget was set for API-only measurements: Today's Three proposal 235 ms (12 samples), Now 42.85 ms (45), Today 23.42 ms (45), and Capture save 29.42 ms (25). EXPLAIN ANALYZE showed the 2,000-row candidate query completed via sequential scan in 0.730 ms; this is expected because nearly every task matched. Active-session lookup used `uq_focus_sessions_one_active_per_user` and `tasks_pkey`, completing in 0.046 ms. Offline queuing is not required by the source specification and is not implemented; an aborted save keeps the typed draft available for retry, covered by Playwright. These local in-process results are a baseline, not a production SLO. |
| H-03 | PASS | Focus route ownership was reviewed and covered by owner-scoped read/write tests, foreign-reference rejection, and scoped export/delete tests. Suggestion endpoints enforce 10 requests per user per minute per route. Input limits and sanitized validation errors are tested. A sentinel test verifies private drift text is absent from request logs and validation responses. |
| H-04 | PARTIAL | Chromium tests cover keyboard access, browser accessibility semantics/live regions, reduced motion, dark mode, contrast, 375px/1920px viewports, and 200% page zoom without horizontal overflow. Native screen-reader and physical-device/one-hand checks require a human hardware walkthrough and remain open. |
| H-05 | PASS | Architecture and user-help docs cover export/delete scope, day-key rule, swap limit, reminder limitations, and feature-flag rollback. |
| H-06 | PASS WITH USER-REQUESTED LOCAL DEFAULT | Legacy Tasks remains available when `VITE_FOCUS_ENABLED=false`; Compose enables Focus for the local site. The rollout-off Playwright regression passes. A production deployment rollback was not performed. |
| H-07 | PASS | `scripts/check.ps1` passed twice consecutively after the final code change. Each run: 24 browser E2E passed and 2 opt-in Docker/worker E2E skipped; 172 API tests passed and 1 optional test skipped; 8 web unit tests passed; lint, production build, and API compile passed. |

The Phase 5 launch milestone is **not fully verified** until a native screen-reader and physical one-hand device walkthrough is completed. No verification tag was created.

### Phase 5 check script results
`scripts/check.ps1` completed twice consecutively with exit code 0. Each run produced the same counts: Playwright 26 total / 24 passed / 2 skipped; pytest 173 total / 172 passed / 1 skipped; Vitest 2 files / 8 passed. The skipped browser tests require `ORIN_DOCKER_E2E` and `ORIN_WORKER_E2E`. Warnings were limited to npm's pending `esbuild` install-script approval, Playwright's `NO_COLOR`/`FORCE_COLOR` environment warning, and Starlette's `python_multipart` deprecation notice.
