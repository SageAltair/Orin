$ErrorActionPreference = 'Stop'
$target = Join-Path $PSScriptRoot 'start-windows-reminders-foreground.ps1'
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($target, [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count -ne 0) { throw 'PowerShell syntax errors in foreground launcher' }
$id = [guid]::NewGuid()
try {
  & $target -PythonPath 'Z:\does-not-exist\python.exe' -ApiUrl 'http://127.0.0.1:8100' -OwnerId $id -WorkspaceId $id -BrowserSessionId $id -LeaseGeneration $id -BrowserOrigin 'http://localhost:5273' -ShortcutPath 'Z:\does-not-exist\shortcut.lnk'
  throw 'Invalid executable was accepted'
} catch {
  if ($_.Exception.Message -notlike '*existing absolute Python executable*') { throw }
}
if (Test-Path Env:ORIN_WINDOWS_REMINDERS_TOKEN) { throw 'Unexpected token environment variable' }
foreach ($case in @(
  @{ Api='http://remote.example'; Origin='http://localhost:5273'; Expected='API must use HTTPS' },
  @{ Api='http://127.0.0.1:8100'; Origin='http://remote.example'; Expected='trusted HTTPS or loopback browser origin' }
)) {
  try {
    & $target -PythonPath (Join-Path $PSHOME 'powershell.exe') -ApiUrl $case.Api -OwnerId $id -WorkspaceId $id -BrowserSessionId $id -LeaseGeneration $id -BrowserOrigin $case.Origin -ShortcutPath $target
    throw 'Untrusted origin was accepted'
  } catch {
    if ($_.Exception.Message -notlike "*$($case.Expected)*") { throw }
  }
}
Write-Output 'PASS: syntax, invalid executable, unsafe API/origin fail-closed, no token environment'
