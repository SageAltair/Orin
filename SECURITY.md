# Security policy

## Supported version

Only the current public release is supported with security updates. Operators must keep the release's pinned dependencies, container images and TLS terminator patched.

## Reporting a vulnerability

Publish a private security contact before launch and direct reports there. Do not ask reporters to include passwords, API keys, access tokens, private user content or production database exports. Acknowledge reports, preserve evidence in a restricted system and coordinate remediation before public disclosure.

## Release requirements

Public releases require protected-branch `verify`, `production-containers`, and `security` checks; HTTPS with tested renewal; managed secrets; a recent verified backup and isolated restore drill; tested monitoring alerts; and a recorded rollback procedure. See `docs/operations.md` for the operational contract and `docs/ai-privacy.md` for external-provider data handling.
