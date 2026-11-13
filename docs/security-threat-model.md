# Orin v1.0 Security Threat Model

**Status:** Engineering baseline for package #180  
**Reviewed:** 2026-11-13  
**Scope:** Authentication, authorization, user data isolation, provider credentials, AI actions, worker execution, and administrative controls.  
**Review boundary:** This document is not an independent penetration test or a claim of OWASP ASVS/MASVS certification. Final integrated penetration testing remains in package #187.

## 1. Security objectives and invariants

Orin must preserve these invariants across every client and API entry point:

1. A user can read or mutate only resources owned by that user and, where applicable, the selected workspace.
2. Passwords, access tokens, refresh tokens, worker credentials, provider API keys, OAuth tokens, and approval secrets must never appear in API responses, logs, URLs, or committed configuration.
3. Revoked or expired sessions and worker credentials fail closed.
4. A refresh-token replay revokes the affected session family rather than silently creating another valid session.
5. AI actions are selected from server-owned schemas and permission metadata. User-supplied model output cannot invent an executable capability or bypass approval.
6. Worker execution is bounded, authenticated, scoped, and isolated from the host network and writable filesystem wherever the sandbox contract applies.
7. CI and acceptance tests use disposable data only. They must not mutate production or real-user data.
8. The frozen #179 API, database, authentication, worker, and notification contracts remain authoritative. Breaking changes require impact analysis, compatibility/migration tests, and recorded approval.

## 2. Assets

| Asset | Security impact if compromised |
|---|---|
| User identity, password hashes, and email | Account takeover, impersonation, recovery abuse |
| Access tokens, refresh tokens, and session records | Persistent account access |
| Tasks, projects, workspaces, Writing/Knowledge content, attachments | Confidentiality loss, unauthorized modification or deletion |
| AI provider credentials and GitHub OAuth tokens | Third-party account access, quota abuse, unexpected charges |
| AI approvals, action payloads, and execution records | Unauthorized actions or loss of accountability |
| Worker device credentials, jobs, and artifacts | Unauthorized execution, data exfiltration, host compromise |
| Admin role and operational controls | Cross-account access and destructive administrative changes |
| Encryption and signing keys | Broad compromise of stored credentials or token integrity |

## 3. Trust boundaries

- **Client to API:** Web, Android, and Windows clients are untrusted. Identity and ownership must be derived from verified server-side credentials, never from client-supplied user IDs.
- **API to database:** Database queries must include owner/workspace predicates. Database credentials and encryption keys are server-side only.
- **API to external providers:** Provider responses and model output are untrusted. Provider credentials are decrypted only for the outbound request and must not be placed in URLs.
- **API to worker:** Worker devices use their own credentials and fixed job scope. A user access token is not a worker credential.
- **Worker to execution sandbox:** Repository content, generated code, package scripts, and artifacts are untrusted inputs. Execution must use fixed arguments, bounded resources, filtered environment, and restricted filesystem/network access.
- **Operator/admin plane:** Administrative role changes and account controls are privileged actions and require auditable attribution.

## 4. Threat scenarios and current controls

| Threat | Existing or implemented controls | Verification evidence | Residual status |
|---|---|---|---|
| Credential stuffing and account enumeration | Argon2 password hashing, dummy-hash verification for unknown users, generic login failures, auth rate limiting | `apps/api/tests/test_auth.py` | Continue monitoring limits and abuse telemetry |
| Refresh-token theft or replay | Opaque high-entropy refresh tokens stored as SHA-256 digests, rotation, replay-family revocation, database-backed session revocation, HttpOnly/SameSite cookie | `apps/api/tests/test_auth.py` | Explicit browser Origin/CSRF policy remains open |
| Cross-account resource access | Owner predicates on user/workspace resources; provider connection lookup binds connection ID and owner ID | `apps/api/tests/test_auth.py`; two-account provider/model regression added in PR #193 | Expand abuse matrix to all provider, attachment, conversation, and approval resources |
| Provider credential disclosure | Fernet/MultiFernet encryption at rest, masked credential hints, no plaintext persistence; PR #193 moves Google discovery key to `x-goog-api-key` header | `apps/api/tests/test_integrations.py`; `apps/api/tests/test_ai_settings.py`; PR #193 | Audit all settings serialization/logging paths; never use query-string credentials |
| OAuth callback forgery or replay | Server-side OAuth state validation and one-time callback state; encrypted stored credentials | `apps/api/tests/test_integrations.py` | Recheck production callback/origin configuration during #186 |
| AI action escalation or prompt injection | Strict server-owned action schemas, immutable registry metadata, permission checks, exact approval binding, execution audit | `apps/api/tests/test_execution.py` | Complete adversarial tests for stale, replayed, cross-user, and modified approvals |
| Worker credential theft or unsafe execution | Hashed worker credentials, signed jobs, fixed scopes, fixed argv, `shell=False`, bounded output/time, filtered child environment, restricted sandbox | Worker capability and worker acceptance suites | Physical client/worker lifecycle verification remains in #184 |
| Privileged admin misuse | Admin-only dependencies, last-admin/self-disable protections, API audit events, and CLI role-change events with an explicit operator identity | `apps/api/tests/test_admin.py`; `apps/api/tests/test_admin_cli.py` | Protect and retain the audit ledger; verify operator identity source in deployment |
| Authentication event coverage | Registration, login, refresh/replay, logout, password/email changes, and session revocation write secret-redacted events to the existing `admin_audit_events` ledger; details contain outcome, request ID, and fixed reason codes only | `apps/api/tests/test_auth.py`; `apps/api/src/orin_api/security_audit.py` | Add alerting/retention policy and verify operational audit access controls |
| Insecure staging configuration | PR #193 requires explicit auth/database/CORS/web settings, HTTPS origins and web URL, and secure refresh cookies for `APP_ENV=staging` | `apps/api/tests/test_config.py`, exact-head CI | Verify against the real staging deployment configuration in #186 |
| Dependency/supply-chain compromise | Locked dependencies, dependency audit, secret scan, container scan, SBOM in CI | Verify Orin security job | Eleven moderate mobile build-tool advisories remain tracked in #21; disposition is required before public launch |

## 5. Open security work

These are explicit gaps, not accepted exceptions:

- **Password recovery:** an unauthenticated, enumeration-safe, rate-limited recovery flow is not implemented. Define a one-time hashed token, short expiry, disposable test outbox, and session-family revocation before enabling real delivery.
- **Browser request integrity:** SameSite=Strict and explicit CORS origins are present, but the refresh route has no explicit Origin/CSRF validation. Test same-site sibling-origin requests and document the chosen mitigation.
- **Secret serialization:** provider API-key settings use hidden repr strings rather than `SecretStr`. Audit every dump/logging path and change types only with an impact review and compatibility tests.
- **Provider input validation:** validate Cloudflare account identifiers against the provider's documented format before interpolating them into request paths.
- **Tenant abuse matrix:** extend two-account tests across provider policies, conversations, attachments, action approvals, and every read/update/delete surface.
- **Independent security assessment:** final penetration testing and release-candidate disposition remain in #187.

## 6. Regression test map

| Area | Test suite |
|---|---|
| Password, login, refresh, replay, logout, session revocation, user isolation | `apps/api/tests/test_auth.py` |
| Provider credential masking, ownership, model selection, routing policy | `apps/api/tests/test_ai_settings.py` |
| OAuth state, credential encryption, key rotation, disconnect | `apps/api/tests/test_integrations.py` |
| AI action schema, permission and approval binding | `apps/api/tests/test_execution.py` |
| Admin authorization and audit behavior | `apps/api/tests/test_admin.py`; `apps/api/tests/test_admin_cli.py` |
| Worker authentication, job lifecycle and sandbox | Worker tests and isolated worker acceptance |
| Staging/production auth configuration | `apps/api/tests/test_config.py` |

## 7. Current implementation evidence

- Foundation contracts are frozen in merged PR [#192](https://github.com/SageAltair/Orin/pull/192), merge commit `308c26cb082b2c7d090f56863ec5967ee459ba74`.
- Security tranche PR [#193](https://github.com/SageAltair/Orin/pull/193) adds staging hardening, safe Google key transport, and two-account provider/model isolation tests.
- Follow-up branch `security/180-auth-and-operator-audit` adds structured authentication events and attributable CLI role-change events using the existing audit table; exact-head CI is pending.
- Exact-head Verify Orin [run #1392](https://github.com/SageAltair/Orin/actions/runs/43328654123) passed 12/12 jobs at the first PR head.
- Exact-head Verify Orin [run #1393](https://github.com/SageAltair/Orin/actions/runs/43329500373) passed 12/12 jobs at commit `5370a2cb0a5be335813c74696c6a5f3eee241e2f`, including backend/worker regression, production containers, security, web/mobile, and isolated browser acceptance.

## 8. Release gates

- No production deployment, real-user data mutation, device/background-service installation, public launch, or paid advertising is authorized by this document.
- Physical Windows and Android delivery checks remain in #184.
- Staging/scalability/operations validation remains in #186.
- Integrated adversarial testing and penetration testing remain in #187.
- The eleven moderate mobile advisories tracked in #21 require documented remediation or explicit risk disposition before public launch.

**Disposition:** This is the committed engineering threat-model baseline for #180. It records current controls and known gaps; it does not mark the open work above as resolved or waive any downstream release gate.
