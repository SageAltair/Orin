$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$apiRoot = Join-Path $repoRoot "apps/api"
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$listener.Start()
$port = $listener.LocalEndpoint.Port
$listener.Stop()
$containerName = "orin-focus-migration-check-$([Guid]::NewGuid().ToString('N'))"
$databasePassword = [Guid]::NewGuid().ToString("N")
$previousDatabaseUrl = $env:DATABASE_URL
$containerStarted = $false

try {
  docker run --detach --rm --name $containerName --env "POSTGRES_USER=postgres" --env "POSTGRES_PASSWORD=$databasePassword" --env "POSTGRES_DB=orin" --publish "127.0.0.1:${port}:5432" --tmpfs "/var/lib/postgresql/data:rw,nosuid,nodev,size=1g" postgres:16-alpine
  if ($LASTEXITCODE -ne 0) { throw "Could not start the isolated PostgreSQL container." }
  $containerStarted = $true

  $ready = $false
  for ($attempt = 0; $attempt -lt 60; $attempt++) {
    docker exec $containerName pg_isready --username=postgres --dbname=orin *> $null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 1
  }
  if (-not $ready) { throw "The disposable PostgreSQL server did not become ready within 60 seconds." }

  $env:DATABASE_URL = "postgresql+psycopg://postgres:${databasePassword}@127.0.0.1:${port}/orin"
  Push-Location $apiRoot
  try {
    python scripts/verify_focus_migrations.py
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL migration verification failed with exit code $LASTEXITCODE." }
  } finally { Pop-Location }
} finally {
  if ($containerStarted) {
    docker stop $containerName *> $null
  }
  if ($null -eq $previousDatabaseUrl) { Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue }
  else { $env:DATABASE_URL = $previousDatabaseUrl }
}
