param([switch]$RunWebChecks)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repo
Write-Host 'Orin local agent readiness (no automatic code changes)'
$branch = (git branch --show-current).Trim()
Write-Host "Branch: $branch"
$changes = @(git status --porcelain)
$unexpected = @($changes | Where-Object { $_ -notmatch '^\?\? docker-compose\.local-recovery\.yml$' })
if ($unexpected.Count -gt 0) { Write-Host ($unexpected -join "`n"); throw 'Working tree has changes; do not start an agent.' }
Write-Host 'Working tree: clean except the intentionally untracked local recovery compose file.'
if ($RunWebChecks) {
  Push-Location (Join-Path $repo 'apps\web')
  try {
    npm test
    if ($LASTEXITCODE -ne 0) { throw 'Web tests failed' }
    npm run lint
    if ($LASTEXITCODE -ne 0) { throw 'Web typecheck failed' }
  } finally { Pop-Location }
}
Write-Host 'Readiness checks complete. No agent was started.'