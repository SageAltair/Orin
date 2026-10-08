# Orin

Orin is an adaptive personal execution environment. The repository includes authenticated project and task APIs and an optional AI-assisted command interpreter. AI interpretation is disabled unless explicitly configured.

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

## AI commands

`POST /api/v1/commands` accepts a natural-language command and returns a safe result. The backend sends the text through the `AIProvider` boundary, validates a strict structured proposal, checks entity ownership and domain schemas, and only then applies one of the predefined task/project/list/activity actions. Provider output never chooses authorization and cannot run SQL, shell commands, or arbitrary code. The existing project/task API remains available independently.

AI is optional. Leave `AI_PROVIDER` empty to run without provider credentials. To enable it, set `AI_PROVIDER` to `openai`, `mistral`, `google`, `openrouter`, `qwen`, `groq`, `cerebras`, or `cloudflare`, set `AI_MODEL`, and supply only the selected provider's API key in `.env`. Cloudflare also requires `CLOUDFLARE_ACCOUNT_ID`. Keep `.env` private; `.env.example` contains placeholders only. Providers are isolated behind adapters; compatible services use the OpenAI chat API format and Google uses its generate-content API.

Initial commands support `CREATE_TASK`, `UPDATE_TASK`, `COMPLETE_TASK`, `CREATE_PROJECT`, `LIST_PROJECTS`, `LIST_TASKS`, and `GET_ACTIVITY`; other requests fail safely. Responses contain application results, not raw provider output. Unit and route tests use fake providers and need no AI credentials.
