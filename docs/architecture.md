# Architecture overview

Orin begins as a modular monolith. `apps/api` owns the HTTP boundary, domain modules, and PostgreSQL access. `apps/web` is a separately built React client. `apps/worker` is an independently runnable process boundary with no queue or execution behavior yet. Shared public TypeScript response shapes live in `packages/contracts`; tiny framework independent utilities may live in `packages/shared`.

The API health liveness route has no infrastructure dependency. Readiness checks the configured database connection. Persistence uses SQLAlchemy 2 and all schema changes must be added as Alembic revisions.
