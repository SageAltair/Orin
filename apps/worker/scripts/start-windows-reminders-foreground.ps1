# Foreground-only opt-in launcher. Never stores or prints the bearer token.
[CmdletBinding()]
param(
  [Parameter(Mandatory)][string]$PythonPath,
  [Parameter(Mandatory)][string]$ApiUrl,
  [Parameter(Mandatory)][guid]$OwnerId,
  [Parameter(Mandatory)][guid]$WorkspaceId,
  [Parameter(Mandatory)][guid]$BrowserSessionId,
  [Parameter(Mandatory)][guid]$LeaseGeneration,
  [Parameter(Mandatory)][string]$BrowserOrigin,
  [Parameter(Mandatory)][string]$ShortcutPath
)
$ErrorActionPreference = 'Stop'
if (-not [Environment]::UserInteractive) { throw 'Interactive desktop session required.' }
if (-not [IO.Path]::IsPathRooted($PythonPath) -or -not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
  throw 'Provide an existing absolute Python executable path.'
}
if (-not [IO.Path]::IsPathRooted($ShortcutPath) -or -not (Test-Path -LiteralPath $ShortcutPath -PathType Leaf)) {
  throw 'Provide an existing absolute registered shortcut path.'
}
$api = [uri]$ApiUrl
if ($api.UserInfo -or $api.Query -or $api.Fragment -or
    -not ($api.Scheme -eq 'https' -or
      ($api.Scheme -eq 'http' -and $api.Host -in @('localhost','127.0.0.1','::1')))) {
  throw 'API must use HTTPS or loopback HTTP without URL credentials.'
}
$origin = [uri]$BrowserOrigin
if ($origin.AbsolutePath -ne '/' -or $origin.Query -or $origin.Fragment -or $origin.UserInfo -or
    -not ($origin.Scheme -eq 'https' -or
      ($origin.Scheme -eq 'http' -and $origin.Host -in @('localhost','127.0.0.1','::1')))) {
  throw 'Provide a trusted HTTPS or loopback browser origin, without a path.'
}
$names = @('TOKEN','ENABLED','API_URL','OWNER_ID','WORKSPACE_ID','BROWSER_SESSION_ID','BROWSER_LEASE_GENERATION','LOCAL_CONTROL_ORIGIN','APP_ID','SHORTCUT')
foreach ($name in $names) {
  if (Test-Path "Env:ORIN_WINDOWS_REMINDERS_$name") {
    throw 'Clear existing reminder environment configuration before starting the isolated foreground launcher.'
  }
}
Write-Host 'Foreground companion only. Keep the authorized Orin browser tab open. Ctrl+C stops it.'
$secret = Read-Host 'Paste a short-lived companion access token (hidden)' -AsSecureString
$pointer = [IntPtr]::Zero
try {
  $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
  $env:ORIN_WINDOWS_REMINDERS_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
  $env:ORIN_WINDOWS_REMINDERS_ENABLED = '1'
  $env:ORIN_WINDOWS_REMINDERS_API_URL = $api.AbsoluteUri.TrimEnd('/')
  $env:ORIN_WINDOWS_REMINDERS_OWNER_ID = $OwnerId.ToString()
  $env:ORIN_WINDOWS_REMINDERS_WORKSPACE_ID = $WorkspaceId.ToString()
  $env:ORIN_WINDOWS_REMINDERS_BROWSER_SESSION_ID = $BrowserSessionId.ToString()
  $env:ORIN_WINDOWS_REMINDERS_BROWSER_LEASE_GENERATION = $LeaseGeneration.ToString()
  $env:ORIN_WINDOWS_REMINDERS_LOCAL_CONTROL_ORIGIN = $origin.GetLeftPart([UriPartial]::Authority)
  $env:ORIN_WINDOWS_REMINDERS_APP_ID = 'Oddly.Orin.Reminders'
  $env:ORIN_WINDOWS_REMINDERS_SHORTCUT = $ShortcutPath
  & $PythonPath -m orin_worker.windows_reminders
  if ($LASTEXITCODE -ne 0) { throw 'Foreground companion exited unsuccessfully.' }
} finally {
  if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
  Remove-Item Env:ORIN_WINDOWS_REMINDERS_TOKEN -ErrorAction SilentlyContinue
  foreach ($name in @('ENABLED','API_URL','OWNER_ID','WORKSPACE_ID','BROWSER_SESSION_ID','BROWSER_LEASE_GENERATION','LOCAL_CONTROL_ORIGIN','APP_ID','SHORTCUT')) {
    Remove-Item "Env:ORIN_WINDOWS_REMINDERS_$name" -ErrorAction SilentlyContinue
  }
}
