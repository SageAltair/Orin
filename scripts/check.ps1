$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location (Join-Path $repoRoot "apps/web")
try {
  npm ci
  if ($LASTEXITCODE -ne 0) { throw "npm ci failed with exit code $LASTEXITCODE" }
  npm audit --omit=dev --audit-level=high
  if ($LASTEXITCODE -ne 0) { throw "production dependency audit failed with exit code $LASTEXITCODE" }
  npm run lint
  if ($LASTEXITCODE -ne 0) { throw "web lint failed with exit code $LASTEXITCODE" }
  npm run test
  if ($LASTEXITCODE -ne 0) { throw "web unit tests failed with exit code $LASTEXITCODE" }
  npm run build
  if ($LASTEXITCODE -ne 0) { throw "web build failed with exit code $LASTEXITCODE" }
  npm run test:e2e -- --workers=1
  if ($LASTEXITCODE -ne 0) { throw "web end-to-end tests failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }

Push-Location (Join-Path $repoRoot "apps/mobile")
try {
  npm ci
  if ($LASTEXITCODE -ne 0) { throw "mobile npm ci failed with exit code $LASTEXITCODE" }
  npm run typecheck
  if ($LASTEXITCODE -ne 0) { throw "mobile typecheck failed with exit code $LASTEXITCODE" }
  npm run test
  if ($LASTEXITCODE -ne 0) { throw "mobile tests failed with exit code $LASTEXITCODE" }
  npm run export:android
  if ($LASTEXITCODE -ne 0) { throw "mobile Android bundle failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }

Push-Location (Join-Path $repoRoot "apps/api")
try {
  python -m pip install -r requirements-dev.lock
  python -m pip install --no-deps -e . -e ../worker
  if ($LASTEXITCODE -ne 0) { throw "API dependency installation failed with exit code $LASTEXITCODE" }
  python -m pip install pip-audit==2.9.0
  if ($LASTEXITCODE -ne 0) { throw "pip-audit installation failed with exit code $LASTEXITCODE" }
  python -m pip_audit -r requirements.lock
  if ($LASTEXITCODE -ne 0) { throw "API dependency audit failed with exit code $LASTEXITCODE" }
  python -m pip_audit -r ../worker/requirements.lock
  if ($LASTEXITCODE -ne 0) { throw "worker dependency audit failed with exit code $LASTEXITCODE" }
  python -m pytest tests ../worker/tests
  if ($LASTEXITCODE -ne 0) { throw "API tests failed with exit code $LASTEXITCODE" }
  python -m alembic upgrade head --sql | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "offline migration check failed" }
  python -m compileall -q src migrations ../worker/src
  if ($LASTEXITCODE -ne 0) { throw "API compile check failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }
