# Orin Engineering Guide

## Product vision

Orin connects human intention with digital execution. In the long term, users will express objectives in natural language and Orin will organize context, coordinate AI agents and computer workers, execute permitted work, request approval when needed, monitor progress, and report results. The repository implements the core personal workspace, a constrained AI command interpreter, Writing/Creative Studio and approval-gated device execution. Extend these only within the requested scope.

## Architecture rules

- Use a monorepo with clear `apps/web`, `apps/api`, and `apps/worker` boundaries.
- Keep the native client in `apps/mobile`; it consumes the existing API and shared contracts and must not duplicate backend domain logic.
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

- `docker compose up --build` — start web, API, and PostgreSQL; the worker is an opt-in profile.
- `docker compose down` — stop services.
- `docker compose down -v` — remove services and local database data.

### Web (`apps/web`)

- `npm install`
- `npm run dev`
- `npm run lint`
- `npm run test`
- `npm run test:e2e` (requires a Playwright browser installed with `npx playwright install chromium`)
- `npm run build`

### Mobile (`apps/mobile`)

- `npm install`
- `npm run android` — launch the Expo Android development client.
- `npm run typecheck`
- `npm test`
- `npm run export:android` — verify the Android JavaScript bundle.

### API (`apps/api`)

- `python -m venv .venv` then activate it.
- `pip install -e ".[dev]"`
- `uvicorn orin_api.main:app --reload`
- `pytest`
- `alembic upgrade head`

### Worker (`apps/worker`)

- `pip install -e apps/worker`
- `orin-worker` — starts the enrolled worker; explicit credentials/roots are required. Project tests require an isolated Linux execution image.

## Rules for future AI coding agents

- Read this file before making changes and inspect the current repository state first.
- Preserve user changes; do not overwrite or remove files without understanding their purpose.
- Keep changes within the requested scope and explain any assumptions.
- Do not add authentication, agent behavior, memory, integrations, or execution until requested.
- Update contracts, migrations, docs, and tests alongside related code changes.
- Run applicable checks and report exact results, including any environmental limitation.
- Never reveal secrets or send messages to external parties unless explicitly authorized.
