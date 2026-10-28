# Hybrid agent setup (safe foundation)

The cloud and Windows paths share GitHub as the source of truth. This initial setup is **readiness-only**, not an autonomous coding agent. It does not run AI models, modify source files, create pull requests, merge, deploy, or access local data.

## Cloud

`.github/workflows/agent-readiness.yml` provides a read-only manual run and a daily scheduled readiness report at 05:17 UTC (08:17 Tanzania time). Scheduled workflows run from the repository's **default branch only**; merge this workflow through review to that branch before expecting the schedule to operate. GitHub may delay scheduled jobs. The report appears in the Actions run summary. No secrets or external AI provider are needed.

The existing `verify.yml` remains the required verification pipeline. Do not grant a cloud agent write access until its execution environment, explicit task allowlist, model/provider credentials, budget, PR-only permissions, and branch protection have been reviewed. Never allow automatic merges or production deployment.

## Windows

Run `powershell -File scripts/agent-local-readiness.ps1` from the repository to verify the current checkout is safe for an agent to start. Add `-RunWebChecks` to run frontend tests and TypeScript checks. The script does not start a coding agent or change the repository. It intentionally tolerates only the untracked local recovery compose file; other modifications stop the check.

## Future agent execution policy

1. One GitHub issue assigned to one agent at a time. Separate branches for local and cloud work, never push directly to the default or recovery branch.
2. Limit each run to one small, reviewable change. Read `AGENTS.md` and preserve existing design constraints.
3. Run focused tests and the full GitHub verification pipeline. Failed tests stop the run. No fabricated test claims.
4. Open draft PRs only. Require human review for merges, permissions, schema changes, external spending, deployments, and destructive actions.
5. Do not use developer `.env` files or production databases in agent environments. Never reset local volumes or run migrations on a non-isolated database.
6. Keep cloud jobs isolated and do not run a local and cloud worker on the same branch simultaneously.
7. Require explicit opt-in to agent costs, provider credentials, GitHub permissions, and execution schedule before enabling code-writing automation.