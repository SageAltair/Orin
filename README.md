# Orin

Orin is an adaptive personal execution environment. This repository is the production-quality monorepo foundation for the product; it intentionally contains no authentication, AI agents, memory, integrations, or task execution.

## Quick start

1. Copy `.env.example` to `.env` and adjust values for your environment. If you change `POSTGRES_PASSWORD`, update its matching password in `DATABASE_URL` too (URL-encode special characters).
2. Run `docker compose up --build`.
3. Open the web app at http://localhost:5173 and API docs at http://localhost:8000/docs.
4. Check API health at http://localhost:8000/health/live and database health at `/health/ready`.

For local development without Docker, see [AGENTS.md](AGENTS.md) and the app READMEs. Database migrations run with `alembic upgrade head` from `apps/api`.

## Repository layout

- `apps/web` React, TypeScript, Vite, Tailwind CSS, shadcn/ui-compatible primitives.
- `apps/api` FastAPI modular monolith, Pydantic settings, SQLAlchemy 2, Alembic.
- `apps/worker` separately deployable worker foundation, currently idle.
- `packages/contracts` explicit API contract definitions.
- `packages/shared` small cross-cutting TypeScript utilities.
- `docs`, `tests`, `scripts`, `infrastructure/docker` supporting project docs and tooling.

## Checks

Run `scripts/check.ps1` on Windows or `scripts/check.sh` on Unix. See [AGENTS.md](AGENTS.md) for detailed commands and development rules.
