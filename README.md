# Orin

Orin is an adaptive personal execution environment. The repository includes authenticated project and task APIs and an optional AI-assisted command interpreter. AI interpretation is disabled unless explicitly configured.

## Quick start

1. Copy `.env.example` to `.env` and adjust values for your environment. If you change `POSTGRES_PASSWORD`, update its matching password in `DATABASE_URL` too (URL-encode special characters).
2. Run `docker compose up --build`.
3. Open the web app at http://localhost:5273 and API docs at http://localhost:8100/docs.
4. Check API health at http://localhost:8100/health/live and database health at `/health/ready`.

The Docker web service runs Vite in development mode. `apps/web` and `packages` are bind-mounted for hot reload, while Linux dependencies live in the `web_node_modules` volume. The image installs from `package-lock.json` with optional dependencies enabled and verifies Linux esbuild during build. The entrypoint checks the lockfile when the container starts and refreshes dependencies if they changed or esbuild is missing. The API source is also bind-mounted and Uvicorn reloads on code changes. Normal source edits do not rebuild either image.

For local development without Docker, see [AGENTS.md](AGENTS.md) and the app READMEs. Database migrations run with `alembic upgrade head` from `apps/api`.

## Repository layout

- `apps/web` React, TypeScript, Vite, Tailwind CSS, shadcn/ui-compatible primitives.
- `apps/mobile` Expo/React Native Android client using the same API, contracts and workspace boundaries.
- `apps/api` FastAPI modular monolith, Pydantic settings, SQLAlchemy 2, Alembic.
- `apps/worker` enrolled device gateway with approved file/system capabilities and isolated project test execution.
- `packages/contracts` explicit API contract definitions.
- `packages/shared` small cross-cutting TypeScript utilities.
- `docs`, `tests`, `scripts`, `infrastructure/docker` supporting project docs and tooling.

## Checks

Run `scripts/check.ps1` on Windows or `scripts/check.sh` on Unix. The GitHub verification workflow also checks PostgreSQL concurrency and migrations. See [AGENTS.md](AGENTS.md) for detailed commands and development rules.

## AI commands

`POST /api/v1/commands` accepts a natural-language command and returns a safe result. The backend sends the text through the `AIProvider` boundary, validates a strict structured proposal, checks entity ownership and domain schemas, and only then applies one of the predefined task/project/list/activity actions. Provider output never chooses authorization and cannot run SQL, shell commands, or arbitrary code. The existing project/task API remains available independently.

AI is optional. Leave `AI_PROVIDER` empty to run without provider credentials. To enable it, set `AI_PROVIDER` to `openai`, `anthropic`, `mistral`, `google`, `openrouter`, `qwen`, `groq`, `cerebras`, or `cloudflare`, set `AI_MODEL`, and supply only the selected provider's API key in `.env`. Cloudflare also requires `CLOUDFLARE_ACCOUNT_ID`. Keep `.env` private; `.env.example` contains placeholders only. Providers are isolated behind adapters; compatible services use the OpenAI chat API format, Anthropic uses its Messages API, and Google uses its generate-content API.

Before enabling AI for public users, review [AI data and provider disclosure](docs/ai-privacy.md) and publish deployment-specific provider and retention terms.

Commands support safe conversational replies plus `CREATE_TASK`, `UPDATE_TASK`, `COMPLETE_TASK`, `CREATE_PROJECT`, `LIST_PROJECTS`, `LIST_TASKS`, and `GET_ACTIVITY`; other requests fail safely. Responses contain application results, not raw provider output. Unit and route tests use fake providers and need no AI credentials.

## Connected workspace

Home, Tasks/Focus, Projects, Calendar, Writing and Activity share a responsive light/dark design. Writing connects the Markdown notes canvas with Idea Inbox, Connections and Manuscript outlines/cards. Notes are versioned, autosaved and recoverable; AI extraction is explicit and respects exclusion controls. Calendar reminders arrive in the private in-app inbox. Account settings support a complete ZIP export and password-confirmed deletion.

Use `BACKGROUND_WORKER_ENABLED=true` for durable analysis recovery and reminders (enabled in Compose and `.env.example`). The device worker is opt-in: enroll in Settings, configure `ORIN_API_URL`, `ORIN_DEVICE_ID`, `ORIN_WORKER_TOKEN` and explicit allowed roots, then run `orin-worker`. Use `docker compose --profile worker up` only after supplying the enrollment settings. See [repair details and limits](docs/reliability-and-design.md) and [operations](docs/operations.md).

Settings now uses section navigation, visual Light/Dark/System choices, and the shared minimal workspace style. See [workspace design](docs/workspace-design.md) for the visual rules and interaction details.

## Opportunities, risks and routines

Opportunities captures possibilities, tracks decisions and links practical next actions to Tasks. Its Risk register records warning signs and response plans. Calendar routines repeat on chosen weekdays with timezone-aware schedules, in-app reminders, minimum versions and reversible check-ins. See [feature details and evidence](docs/opportunities-and-routines.md).

## Intelligent notifications

Settings → Notifications & follow-up controls automatic reminders for tasks, scheduled work, project/milestone dates, calendar/routines, reviews, approvals and failures. Optional persistent follow-up has quiet hours, snooze, acknowledgement and repeat limits. Browser alerts/audio require explicit opt-in and Orin open; device silent/DND settings remain in control. See [notification behavior and limits](docs/intelligent-notifications.md).

## Verification and production

Install Python dependencies with the resolved `apps/api/requirements-dev.lock`, then install API/worker packages with `--no-deps`. Frontend checks use `npm ci` and the committed npm lockfile. Install Chromium using `npx playwright install chromium` before browser tests.

`ORIN_LIVE_E2E=true` enables live Writing/Studio flows with an isolated API at `http://localhost:8100`. The default browser suite does not require a live API. Optional Docker/provider and real worker tests retain their separate opt-in flags.

`docker-compose.production.yml` is a reviewable deployment template with a built frontend and same-origin API proxy. Configure HTTPS through a host TLS terminator, production origin settings, private secrets, backups and monitoring before exposing it. No deployment is performed by this repository change.

## Administration

Administration runs as a separate protected console at `http://localhost:5273/admin`; it is not embedded in the personal workspace. After registering the owner account and applying migrations, grant access explicitly from the API container:

```powershell
docker compose exec api python -m orin_api.admin_cli promote owner@example.com
```

Sign in at `/admin` to load the console. It reports aggregate system, AI, storage, approval, session, worker and workspace health. Administrators can manage roles and account status, revoke sessions and worker devices, remove empty workspaces, close registration, and run safe expired-record cleanup. It does not expose credentials, command text, document contents or attachment contents. Remove access with the same command using `demote`.
