$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location (Join-Path $repoRoot "apps/web")
try {
  npm install
  npm run lint
  npm run test
  npm run build
  npm run test:e2e
} finally { Pop-Location }

Push-Location (Join-Path $repoRoot "apps/api")
try {
  python -m pip install -e ".[dev]"
  python -m pytest
  python -m compileall -q src migrations
} finally { Pop-Location }
