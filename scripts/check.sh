#!/usr/bin/env sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT/apps/web"
npm install
npm run lint
npm run test
npm run build
npm run test:e2e
cd "$ROOT/apps/api"
python -m pip install -e '.[dev]'
python -m pytest
python -m compileall -q src migrations
