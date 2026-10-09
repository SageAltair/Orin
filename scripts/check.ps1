$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location (Join-Path $repoRoot "apps/web")
try {
  npm install
  if ($LASTEXITCODE -ne 0) { throw "npm install failed with exit code $LASTEXITCODE" }
  npm run lint
  if ($LASTEXITCODE -ne 0) { throw "web lint failed with exit code $LASTEXITCODE" }
  npm run test
  if ($LASTEXITCODE -ne 0) { throw "web unit tests failed with exit code $LASTEXITCODE" }
  npm run build
  if ($LASTEXITCODE -ne 0) { throw "web build failed with exit code $LASTEXITCODE" }
  npm run test:e2e -- --workers=1
  if ($LASTEXITCODE -ne 0) { throw "web end-to-end tests failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }

Push-Location (Join-Path $repoRoot "apps/api")
try {
  python -m pip install -e ".[dev]"
  if ($LASTEXITCODE -ne 0) { throw "API dependency installation failed with exit code $LASTEXITCODE" }
  python -m pytest
  if ($LASTEXITCODE -ne 0) { throw "API tests failed with exit code $LASTEXITCODE" }
  python -m compileall -q src migrations
  if ($LASTEXITCODE -ne 0) { throw "API compile check failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }
