# Experimental Windows task reminders

This optional **foreground** companion polls Orin's existing authenticated Tasks
API and displays a generic Windows toast 30 minutes before a task is due.
It is **not enabled by default**, not an installed service, and not proof of
delivery when Orin is closed, Windows is asleep, or notifications are suppressed.

## Privacy and safety

- Requires explicit `ORIN_WINDOWS_REMINDERS_ENABLED=1`, an active user bearer
  token, the matching owner UUID, and a workspace UUID. Credentials are held
  only in process memory and are **never stored** in the SQLite reminder queue.
- Reads tasks only with `X-Orin-Workspace-Id`. The queue contains only scoped
  task identifiers, due timestamps and toast-attempt markers, never task names.
  A different owner/workspace clears previous queue entries. A single-instance file lock prevents concurrent companions from double-alerting.
- Checks live authentication, current task state and notification preferences
  before each delivery pass, then **rechecks authentication and suppression policy
  immediately before a due toast**. Changes to task opt-in, quiet hours or Focus
  suppression during a slow task scan take effect before delivery. HTTP 401/403
  or owner mismatch clears the queue. Network failure fails closed without
  delivering cached reminders. A still-valid independently supplied token cannot
  detect browser logout without a client-controlled session bridge.
- For multi-page task lists, performs a confirming read of all task identities,
  statuses and due timestamps before replacing the durable queue. This detects
  many offset-pagination shifts caused by concurrent edits or deletions, but
  cannot provide a database snapshot or guarantee against all races. A changed
  read fails closed and retries on the next poll without consuming reminders.
  Large lists require additional API requests.
- Opting out of tasks notifications clears the local queue on the next
  successful sync. Quiet hours are respected. No silent/DND bypass.
- When the server's `respect_focus` preference is enabled, checks the authenticated `/focus-sessions/active` endpoint before a due alert. Unlike the 50-row Focus history, this owner-scoped endpoint includes older active sessions, even without an associated task, and expires elapsed sessions. Active sessions suppress delivery; missing, malformed or unavailable Focus state fails closed. This requires an API version with the active-state endpoint. Tests do not establish real Windows acceptance.
- Equal quiet-hours start/end bounds mean quiet all day, matching the API policy.
- The current Orin web logout flow does not necessarily revoke an independently
  supplied bearer token. Stop this process and revoke its token on logout or
  account change. A fully integrated session lifecycle is **not implemented**.
- Windows toast attempts now fail closed unless an existing absolute Start Menu
  `.lnk` path and a syntactically valid AppUserModelID are explicitly configured.
  The PowerShell transport checks that the shortcut exposes the same registered
  `System.AppUserModel.ID` before calling `Show`. It resolves Windows PowerShell
  from the OS-reported system directory instead of searching `PATH`, and fails
  closed if the system executable is unavailable. It does not install or
  register a shortcut. These guards are covered only by isolated tests.
- Toast transport still requires an interactive user session and OS acceptance.
  It has **not** been verified on a real Windows desktop. Do not treat subprocess
  success as visible delivery.

## Developer-only manual opt-in (after local Windows acceptance)

Install the worker in a virtual environment and launch
`orin-windows-reminders` in the signed-in user's session after setting:
`ORIN_WINDOWS_REMINDERS_ENABLED=1`,
`ORIN_WINDOWS_REMINDERS_API_URL=https://<trusted-api>`,
`ORIN_WINDOWS_REMINDERS_TOKEN=<short-lived-user-token>`,
`ORIN_WINDOWS_REMINDERS_OWNER_ID=<owner-uuid>`,
`ORIN_WINDOWS_REMINDERS_WORKSPACE_ID=<workspace-uuid>`,
`ORIN_WINDOWS_REMINDERS_APP_ID=<registered-AppUserModelID>`, and
`ORIN_WINDOWS_REMINDERS_SHORTCUT=<absolute-Start-Menu-Programs-lnk-path>`.
The shortcut must already exist in the current-user or all-users Start Menu
Programs directory and expose that exact AppUserModelID. Missing, mismatched,
or unregistered identity fails without marking any reminder as attempted.
Do not create or install a shortcut during automated tests.
Use an HTTPS API, or loopback HTTP for local development. Do not put bearer
tokens into tracked scripts, PowerShell history, screenshots, or logs.

A successful toast API call is recorded as an attempt, not proof the alert was visible.
The companion must be stopped when switching accounts or workspaces until
a client-controlled session bridge is implemented.

This process stops with Ctrl+C, does not auto-start, and does not install
anything on a phone. It does not claim to wake a sleeping or powered-off device.
The OS toast adapter and lifecycle still require real Windows validation.

## Tests

`python -m pytest apps/worker/tests/test_windows_reminders.py -q`

Tests use disposable SQLite, fake clocks, mocked HTTP and fake notifiers.
No real notifications, accounts or production data are touched.
