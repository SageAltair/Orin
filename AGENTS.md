# Orin Engineering Guide

## Product vision

Orin connects human intention with digital execution. In the long term, users will express objectives in natural language and Orin will organize context, coordinate AI agents and computer workers, execute permitted work, request approval when needed, monitor progress, and report results. This repository establishes the platform foundation only. Do not implement authentication, AI agents, memory, integrations, or execution without a specific request.

## Architecture rules

- Use a monorepo with clear `apps/web`, `apps/api`, and `apps/worker` boundaries.
- Start with a modular monolith; do not introduce microservices or unnecessary dependencies.
- Keep domain logic separate from HTTP, persistence, and framework code.
- Put public API shapes in `packages/contracts`; keep provider and worker implementations behind replaceable interfaces.
- Configuration comes from environment variables. Never commit secrets or hard-code credentials.
- PostgreSQL schema changes must be represented by Alembic migrations.
- Keep API contracts explicit, versionable, and documented.
- Do not introduce product features beyond the requested scope.

## Coding standards

- TypeScript strict mode; use typed interfaces and avoid `any`.
- Python 3.12+, type annotations, Pydantic v2, SQLAlchemy 2 style.
- Prefer small, cohesive modules and dependency injection at application boundaries.
- Validate external input and return stable, intentional error responses.
- Keep dependencies minimal and pinned or constrained deliberately.
- Use accessible semantic HTML and reusable UI primitives.

## Testing requirements

- Add focused tests for every meaningful feature and bug fix.
- Frontend unit tests use Vitest; browser flows use Playwright.
- Backend tests use pytest and must not require a developer's local database unless explicitly configured.
- Run the repository check script before handing off changes. Do not claim a check passed unless it was run.
- Keep tests deterministic and avoid real external service calls.

## Security rules

- Never store secrets in source control, logs, fixtures, or images.
- Use environment-based configuration and fail clearly on invalid configuration.
- Restrict CORS to configured origins; do not enable wildcard origins with credentials.
- Apply least privilege to services and database users in deployed environments.
- Validate inputs, avoid unsafe SQL/string interpolation, and do not expose internal exception details.
- Use HTTPS and secure secret management in production deployments.

## Commands

### Docker

- `docker compose up --build` — start web, API, PostgreSQL, and idle worker.
- `docker compose down` — stop services.
- `docker compose down -v` — remove services and local database data.

### Web (`apps/web`)

- `npm install`
- `npm run dev`
- `npm run lint`
- `npm run test`
- `npm run test:e2e` (requires Chrome or a Playwright browser installed with `npx playwright install chromium`)
- `npm run build`

### API (`apps/api`)

- `python -m venv .venv` then activate it.
- `pip install -e ".[dev]"`
- `uvicorn orin_api.main:app --reload`
- `pytest`
- `alembic upgrade head`

### Worker (`apps/worker`)

- `pip install -e apps/worker`
- `orin-worker` — starts the idle worker process; no jobs are executed.

## Rules for future AI coding agents

- Read this file before making changes and inspect the current repository state first.
- Preserve user changes; do not overwrite or remove files without understanding their purpose.
- Keep changes within the requested scope and explain any assumptions.
- Do not add authentication, agent behavior, memory, integrations, or execution until requested.
- Update contracts, migrations, docs, and tests alongside related code changes.
- Run applicable checks and report exact results, including any environmental limitation.
- Never reveal secrets or send messages to external parties unless explicitly authorized.


## Execution contract: scope, verification, and friction

These rules apply to every implementation, bug fix, and design change. They supplement, rather than replace, the architecture, security, and testing requirements above.

### Execute the request, not an expanded interpretation

- Inspect the relevant code, existing behavior, tests, and working tree before editing. Identify the smallest set of affected modules.
- Implement the requested behavior within existing architecture. Do not add unrelated features, redesigns, dependencies, migrations, or refactors.
- If the instruction is actionable, proceed without unnecessary preference questions. Ask only when an essential ambiguity creates a meaningful risk.
- Preserve working behavior and user data. Do not discard uncommitted changes.
- For larger requests, work through coherent, verifiable user journeys. Keep a short internal checklist; do not substitute a plan for delivery.

### Completion requires evidence

Use the following meanings consistently:
- **Implemented:** relevant code has changed, but the end-to-end behavior may not be verified.
- **Verified:** the applicable automated checks and real user journey passed in an available environment.
- **Unverified:** the check could not be run or evidence is insufficient.
- **Blocked:** a specific prerequisite prevents further progress.

Before calling a user-facing feature **COMPLETE**, confirm, where applicable:
1. The user can reach it through the real application, not just an unmounted component or isolated endpoint.
2. Frontend, API, permissions, persistence, worker, and relevant navigation are integrated.
3. Its principal user journey works, including error, loading, and empty states.
4. Changes survive navigation or refresh when persistence is expected.
5. Targeted tests pass and directly affected existing workflows have not regressed.
6. Responsive layouts and supported themes have been visually inspected when rendering/browser tools are available.

If an essential criterion cannot be checked, mark the work **PARTIAL** or **UNVERIFIED** and explain exactly why. Never report a test as passed unless it ran.

### Debugging and testing without loops

- Reproduce the defect or identify a concrete failing contract before changing code whenever practical.
- Prefer a focused failing regression test, fix the underlying cause, then rerun that test.
- After two unsuccessful attempts on the same defect, stop applying variants of the same patch. Reinspect assumptions, architecture, state flow, and interfaces before proceeding.
- Do not repeatedly run identical failing commands without a relevant change or new diagnostic purpose.
- Match tests to impact: visual changes need rendering checks; API changes need contract/integration tests; database changes need migration and persistence checks; cross-module changes need a user-journey test.
- Run broader checks when justified by change impact and before handoff where the environment permits. Clearly separate environment failures from application defects.
- Avoid repeated full builds, broad scans, and unnecessary status narration that do not improve confidence.

### Design and interaction quality

- Follow Orin's established minimal, professional, premium visual language. Use shared components, design tokens, accessible semantics, and consistent spacing, typography, hierarchy, and interaction states.
- Reduce steps for common actions; use inline editing, contextual actions, and progressive disclosure where appropriate.
- Avoid excessive cards, buttons, nested panels, oversized controls, and confirmation dialogs.
- Preserve responsive behavior and light/dark theme support. Do not redesign unrelated screens.
- Inspect the rendered result when possible. Source inspection alone is not visual verification.
- Do not claim visual polish or pixel accuracy without a rendered inspection.

### Integration and reliability

- Reuse the canonical domain model and existing services; avoid duplicate task, note, project, notification, or AI state.
- Keep frontend/backend contracts aligned, including partial-update semantics.
- Protect tenant/user ownership, permissions, and privacy boundaries; test these on affected endpoints.
- Prevent lost writes on autosave, navigation, retries, and concurrent edits where relevant.
- Centralize provider error handling and distinguish timeout, quota, authentication, fallback, and streaming failures. Never assume live AI provider reliability from mocked tests.
- A feature that exists in code but is not reachable or operational must be described as incomplete.

### Required final handoff

Report concisely using these exact headings:
- **Implemented:** concrete behavior changed.
- **Verified:** checks run and their actual outcomes, including user journeys.
- **Unverified:** missing checks or environment limitations.
- **Remaining:** known defects, follow-ups, or blockers.
- **Files changed:** paths touched.
- **Status:** **COMPLETE**, **PARTIAL**, or **BLOCKED**.

Do not use **COMPLETE** when essential acceptance criteria remain unverified. Do not claim a bug is fixed without relevant verification. Do not continue adding scope after meeting the acceptance criteria.

**Operating rule: Do the requested work. Integrate it. Verify it. Report the truth. Stop.**
