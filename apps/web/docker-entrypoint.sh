#!/bin/sh
set -eu

lock_hash="$(sha256sum package-lock.json | cut -d ' ' -f 1)"
installed_hash="$(cat node_modules/.orin-package-lock-hash 2>/dev/null || true)"

if [ "$lock_hash" != "$installed_hash" ] || [ ! -x node_modules/@esbuild/linux-x64/bin/esbuild ]; then
  npm ci --include=optional --ignore-scripts --no-audit --no-fund --fetch-timeout=30000 --fetch-retries=1
  printf '%s\n' "$lock_hash" > node_modules/.orin-package-lock-hash
fi

exec npm run dev -- --host 0.0.0.0
