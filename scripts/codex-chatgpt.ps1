param([switch]$Review)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not (Get-Command codex -ErrorAction SilentlyContinue)) { throw 'Install Codex CLI: npm install -g @openai/codex' }
$auth = (& codex login status 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $auth -notmatch 'Logged in using ChatGPT') { throw 'Sign in interactively using: codex login (choose ChatGPT account, not API key)' }
if ($Review) {
  $prompt = 'Read AGENTS.md and inspect repository code and tests. Read-only review. Do not modify files, access secrets, run migrations, or use the network. Identify one small high-impact improvement with evidence and tests; do not claim tests ran.'
  $prompt | & codex exec --sandbox read-only --cd $repo -
} else {
  Write-Host 'Starting Codex with your ChatGPT subscription. Review changes before committing or merging.'
  & codex --cd $repo
}
exit $LASTEXITCODE