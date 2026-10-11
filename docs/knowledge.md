# Personal knowledge workspace

The Knowledge workspace stores user-authored notes, drafts, decisions, research and related document links. Documents keep a versioned source of truth, an independent lifecycle status, optional project/review date, archive control and an AI exclusion flag. Quick capture is available from Home.

## Retrieval and reports

Document search and the no-provider Ask fallback use bounded keyword ranking. Ask can use the configured provider to synthesize from retrieved, owned, non-archived and non-excluded records; the response returns citations to those records. Semantic embeddings are not currently available, so the interface reports keyword-only mode when synthesis is unavailable.

Daily, weekly, monthly, topic, writing and decision reports use document metadata and text matching. They exclude journals and AI-excluded documents, report sparse evidence plainly, and link observations to their source records. Deterministic signals include recurring and rising terms, dormant ideas, unfinished drafts and repeated blockers from existing task return points. These are evidence summaries, not claims about importance or intent.

## Extraction and privacy

Extraction is an explicit, optional action. The API records one job per document version, validates provider output against a versioned Pydantic schema and retries transient/invalid output up to three times. The source text is never overwritten. Candidate actions are displayed for review and do not create tasks. A source edit, archive, or AI exclusion supersedes pending work; exclusions remove stored extracted data and hide it from retrieval, analysis and reports.

Jobs run as API background work and are stored in PostgreSQL. A processing job older than ten minutes can be re-queued when the user retries extraction. The API does not yet run a continuous recovery worker, so a queued job left by a process restart needs a user retry. Configure `AI_PROVIDER` and `AI_MODEL` in the environment to enable extraction and synthesis; all writing and non-AI features remain available without them.

## Local verification

Start the stack with `docker compose up --build`; the API container runs Alembic migrations before starting. Open the web app at `http://localhost:5273`. The repository check is `scripts/check.ps1` on Windows or `scripts/check.sh` on Unix. Tests should use provider-free settings or mock the provider; do not use a real provider for fixtures containing private text.
