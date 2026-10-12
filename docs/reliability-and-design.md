# Reliability and interface repair

This change repairs the 12 October audit on top of `feature/focus-tasks`. It preserves the existing project, task, focus, chat and writing models while connecting the additional studio tools.

## What changed

- Creative cards and outline items validate referenced document ownership; parents must belong to the same owned project. Card PATCH accepts partial changes and explicit nulls.
- Document updates lock the owned row before checking its version. Old-client updates return 409. Prior versions are retained.
- Writing saves before changing notes, creating a note, archiving, requesting analysis or moving to another studio view. Edits made during a save use the returned version. Failed saves stop automatic retries and expose Retry save.
- Full draft metadata is cached under a user-and-document key. Conflicting local drafts survive a newer server version and can be restored explicitly; version history retains the replaced server text. Browser/device loss still limits local recovery.
- AI exclusion/archive/content changes invalidate affected derived insights. Insight reads reconcile eligible sources. Journals are excluded from extraction and note synthesis as well as reports.
- Main chat can retrieve relevant owned Writing excerpts. Ask-your-notes searches matching older records in storage rather than only the latest 500. Notes have offset pagination; reports/signals remain bounded analyses and are not semantic search.
- Persisted extraction jobs recover after interruption. Row locks prevent duplicate processing. Stale processing/retrying jobs are eligible for recovery after ten minutes.
- Calendar reminders are deduplicated, durable in-app notifications. The API background service processes them every 15 seconds; the app refreshes its inbox every 30 seconds. All-day reminders use 09:00 in the event's timezone. Missed reminders catch up until one hour after the event starts. This does not send email, SMS or operating-system push alerts.
- Authentication and costly note/upload operations have database-backed rate limits. Configure edge limits and trusted proxies as described in operations.
- Account export contains owned records and attachment bytes, excluding authentication/integration credentials. Account deletion requires the password and explicit DELETE confirmation, cascades user-owned rows and removes attachment bytes.
- Registered actions run in an execution-owned savepoint; route adapters cannot commit partial mutations. Conservative requests approval for every registered change, Balanced permits low risk, and Automatic permits low/medium risk. Protected actions and all device jobs still require approval.
- Worker restart reconciliation reports interrupted execution as uncertain/failed instead of blindly replaying it. Server maintenance expires overdue queued/running jobs.
- Project test commands require a separately provisioned Linux Docker execution image. Only a bounded, sanitized source snapshot is mounted; no live project, credential files, VCS configuration or symlinks are exposed. The container has no network, a read-only root/source, dropped capabilities and CPU/memory/process limits. The default worker cannot run project tests without that image. File/system jobs remain available on enrolled Windows workers.
- Docker services run as a non-root user. Python builds use resolved dependency locks. Generated test/build artifacts are removed from version control.
- Offline SQL generation works through the full migration graph, including a 128-character Alembic revision column.

## Interface

The shared design system defines light/dark surfaces, readable text contrast, consistent spacing, radii, controls and focus styles. Home, chat, projects, calendar, settings and embedded focus share the same vocabulary. Writing has Notes, Idea Inbox, Connections and Manuscript views. Manuscript supports section kinds/hierarchy, ordering, statuses and purpose cards. Template ideation prompts are labelled prompts, not AI-generated results.

Writing is loaded as a separate bundle. Its list/editor own their scrolling. Narrow phones switch between list and editor; short landscape layouts reduce the header. Reduced-motion and keyboard focus behavior remain supported.

## Checks and operating limits

Run `scripts/check.sh` or `scripts/check.ps1`. Browser checks use Playwright's installed Chromium rather than requiring a machine-specific Chrome installation. `ORIN_BROWSER_EXECUTABLE_PATH` can override the executable. Set `ORIN_LIVE_E2E=true` with an isolated API at port 8100 to run live writing/studio tests. Never run destructive concurrency fixtures against an existing database.

The GitHub workflow uses an isolated PostgreSQL service for concurrency, schema upgrade, schema comparison and offline SQL checks, then runs browser flows against that API. Unit tests use fake providers and isolated fixtures.

Cloud execution, live GitHub OAuth credentials, external notification channels, email verification/reset/MFA and live AI provider certification remain integration/deployment work. No cloud account or paid resources are provisioned by this source change. The production Compose template is supplied for review; it is not a deployment.

## Branch integration

The repository's default main branch previously contained only a README. This repair must be integrated into main for default-branch tools to see the complete application. Keep the feature history, validate the PR, and use the GitHub review rather than force-pushing unrelated histories.
