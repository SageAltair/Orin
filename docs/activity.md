# Activity timeline

Orin extends its existing `activity` table for the user-visible workflow timeline. Activity rows remain scoped to `user_id`; command, execution, approval, worker job, project, and task references are optional so unrelated events do not need synthetic parent records.

The API exposes `GET /api/v1/activity` with `limit`/`offset` pagination and optional `project_id`, `event_type`, `status`, `execution_id`, `command_id`, `since`, and `until` filters. `GET /api/v1/activity/{id}` applies the same user ownership boundary. The Activity page requests one page at a time and supports event-type filtering and incremental loading.

Command receipt, interpreted intent, validated plan, policy decisions, approval requests and decisions, worker connection/revocation, and worker job queue/start/progress/terminal transitions are recorded at their owning API boundaries. Progress events are deduplicated per job state and contain no worker-supplied message. Retry-sensitive events have a unique `(user_id, idempotency_key)` constraint. Metadata is restricted to known scalar fields and rejects secret-like values; prompts, worker results, and arbitrary command output are not copied into the timeline. GitHub connect, disconnect, repository listing/selection, and context reads add integration operation events.

Apply the Alembic chain with `alembic upgrade head` through the normal database migration process. PostgreSQL enum values are additive and retained by downgrade because PostgreSQL does not safely remove enum values in place. No new environment variables are required for the activity timeline itself.

The timeline records state transitions currently owned by the API. It does not claim to represent AI internal reasoning or events the API cannot observe. There is no cloud Worker, so cloud execution events cannot occur. Apply all migrations in revision order through the normal database migration process; do not downgrade production data without a backup and an explicit recovery plan.
