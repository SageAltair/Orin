#!/usr/bin/env sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT/apps/web"
npm ci
npm run lint
npm run test
npm run build
npm run test:e2e
cd "$ROOT"
python -m pip install -r apps/api/requirements-dev.lock
python -m pip install --no-deps -e apps/api -e apps/worker
python -m pytest apps/api/tests apps/worker/tests
python -m compileall -q apps/api/src apps/api/migrations apps/worker/src
cd apps/api
python -m alembic heads
python -m alembic upgrade head --sql > /dev/null
