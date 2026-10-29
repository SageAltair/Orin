# Orin development with ChatGPT Codex

## Local Windows

Run `codex login` and choose **Sign in with ChatGPT**, not API key. Codex CLI is already installed and ChatGPT-authenticated on the development computer. From repository root run `powershell -ExecutionPolicy Bypass -File scripts/codex-chatgpt.ps1 -Review` for read-only analysis or omit `-Review` for interactive development. ChatGPT Codex usage limits apply; wait for reset if exhausted.

## Cloud while Windows is off

Visit https://chatgpt.com/codex and connect the GitHub repository `SageAltair/Orin`. Create a Codex Cloud environment for that repository, and first request a read-only audit. Cloud tasks run independently of the PC. For code changes, use feature branches, run tests, and require pull request review before merging. Account eligibility and usage limits apply.

## Security and legacy workflow

Never export or copy ChatGPT login/session credentials into GitHub Actions. `.github/workflows/codex-review.yml` is API-key-based and cannot use ChatGPT subscription authentication. Do not run that workflow for subscription-based Codex. Keep secrets out of logs and do not auto-merge, deploy, or run migrations.