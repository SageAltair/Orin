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
  Large lists require additional API requests. Before each due toast, another authenticated scan verifies that due tasks remain active with unchanged deadlines. This is a best-effort check, not an atomic guarantee against edits after the scan.
- Opting out of tasks notifications clears the local queue on the next
  successful sync. Quiet hours are respected. The production loop rechecks
  the current wall clock immediately before attempting a toast, so a long
  task scan that crosses into quiet hours does not use the stale poll-start
  time. This is still best-effort: an OS alert can be suppressed independently,
  and a preference change after the final server read is not atomic. No
  silent/DND bypass.
- When the server's `respect_focus` preference is enabled, checks the authenticated `/focus-sessions/active` endpoint before a due alert. Unlike the 50-row Focus history, this owner-scoped endpoint includes older active sessions, even without an associated task, and expires elapsed sessions. Active sessions suppress delivery; missing, malformed or unavailable Focus state fails closed. This requires an API version with the active-state endpoint. Tests do not establish real Windows acceptance.
- Equal quiet-hours start/end bounds mean quiet all day, matching the API policy.
- Due timestamps are validated against real calendar dates and strict ISO date/time
  syntax with explicit timezone offsets no greater than 14 hours. Malformed
  deadlines fail closed before replacing the reminder queue; Python's permissive
  ISO parser alone would accept invalid offsets such as `+15:00`.
- **Required short-lived browser workspace lease:** In Orin Settings → Notifications,
  explicitly enable the Windows companion browser lease for the current tab.
  The browser creates a fresh generation for the selected workspace, renews
  it every 10 seconds and expires it after 45 seconds without renewal.
  On a workspace switch the browser must receive server confirmation that the
  previous lease was revoked **before** showing the new workspace. A stale
  generation, revoked session, expired lease, owner/workspace mismatch or
  unreachable lease API prevents the companion from delivering. Revocation or
  malformed identity clears the scoped queue; a transient lease/session API
  outage drops pending alerts but retains attempted-delivery markers so
  recovery does not duplicate earlier toasts. Browser lease state is stored
  server-side without tokens.
  The companion must be started with the browser's current session UUID and
  lease-generation UUID shown in Notifications settings. These IDs are not
  access credentials; the companion still needs its own short-lived bearer.
  Browser tab closure attempts a best-effort authenticated revoke request,
  but closure and sleep are bounded by lease expiry, **not** guaranteed
  immediate revocation. Failed server logout cannot be guaranteed instantaneous
  if the browser cannot contact the API. The browser must remain active for
  renewals, and a renewed browser lease does not renew the companion's access
  token. No automatic startup or persistent credentials are installed.
- Windows toast attempts now fail closed unless an existing absolute Start Menu
  `.lnk` path and a syntactically valid AppUserModelID are explicitly configured.
  The PowerShell transport checks that the shortcut exposes the same registered
  `System.AppUserModel.ID` before calling `Show`. It resolves Windows PowerShell
  from the OS-reported system directory instead of searching `PATH`, and fails
  closed if the system executable is unavailable. It does not install or
  register a shortcut. An explicitly invoked, opt-in registration utility
  is now available; it never runs automatically.
- Toast transport still requires an interactive user session and OS acceptance.
  It has **not** been verified on a real Windows desktop. Do not treat subprocess
  success as visible delivery.

## Explicit per-user shortcut registration (opt-in only)

On the signed-in Windows desktop, activate the **isolated worker virtual
environment** and choose its actual Python executable. Preview or install the
Orin-owned shortcut (no elevation, no service, no scheduled task, no API token):

~~~powershell
$python = (Get-Command python).Source
.\apps\worker\scripts\register-windows-reminder-shortcut.ps1 -Install -PythonPath $python -WhatIf
.\apps\worker\scripts\register-windows-reminder-shortcut.ps1 -Install -PythonPath $python
~~~

The script creates only the current user's
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Orin Task Reminders.lnk
with the Oddly.Orin.Reminders AppUserModelID. Its target is the chosen Python
executable and its arguments are only -m orin_worker.windows_reminders.
No credentials, environment secrets, auto-start entry, service or scheduled
task are written. It will not replace an existing unrelated or differently
configured shortcut. Repeating installation is a no-op if identity, target
and arguments already match. To remove **only** a matching Orin shortcut:

~~~powershell
.\apps\worker\scripts\register-windows-reminder-shortcut.ps1 -Remove
~~~

After installation, configure ORIN_WINDOWS_REMINDERS_APP_ID=Oddly.Orin.Reminders
and ORIN_WINDOWS_REMINDERS_SHORTCUT to the absolute path shown by the script,
then run orin-windows-reminders-check. This confirms the shortcut metadata,
**not** visible delivery. The foreground companion still needs explicit opt-in,
a short-lived token and real interactive acceptance; do not run it merely
because the shortcut exists.

Windows CI verifies creation, identity, idempotence, wrong-identity refusal,
removal and -WhatIf **only inside a disposable runner profile**, never the
runner's real Start Menu. It sends no toast. This does not establish behavior
on the original Windows device.

## Read-only Windows shortcut diagnostic

On a Windows desktop, install the worker in an isolated virtual environment,
then configure only `ORIN_WINDOWS_REMINDERS_APP_ID` and
`ORIN_WINDOWS_REMINDERS_SHORTCUT` to point at an **existing** Start Menu
shortcut with its matching registered AppUserModelID. Run:

```powershell
orin-windows-reminders-check
```

This checks the shortcut's actual `System.AppUserModel.ID` using the
OS-provided Windows PowerShell. It does **not** send a toast, create a
shortcut, register an identity, start the companion, contact the API, or
require a bearer token. Failure exits nonzero and makes no changes.
A passing diagnostic confirms only registration metadata, not that a toast
was visible or that Windows allows notifications. Interactive delivery
acceptance remains mandatory. See Microsoft's
[desktop toast AppUserModelID requirements](https://learn.microsoft.com/en-us/windows/win32/shell/enable-desktop-toast-with-appusermodelid).

## Manual visible-toast acceptance (one shot, explicit consent)

After the **read-only** registration diagnostic passes on the signed-in Windows
desktop, the user can request **one generic test toast** without an API token,
task, reminder database or running companion. This is never invoked by CI,
the scheduler or the shortcut installer. Set the existing
`ORIN_WINDOWS_REMINDERS_APP_ID` and `ORIN_WINDOWS_REMINDERS_SHORTCUT` to
the already registered identity, then deliberately opt in for this one test:

~~~powershell
$env:ORIN_WINDOWS_REMINDERS_TEST_TOAST = '1'
try {
    orin-windows-reminders-test
} finally {
    Remove-Item Env:\ORIN_WINDOWS_REMINDERS_TEST_TOAST -ErrorAction SilentlyContinue
}
~~~

The toast body says **"This is a test notification."** It never contains task
names or secrets. The command checks the existing shortcut's AppUserModelID
before calling the Windows toast API and does not install or register anything.
A successful command means only that Windows accepted the *request*. Verify
the banner and Notification Center **visually** in the interactive desktop
session, with Windows app notifications enabled and Focus/Do Not Disturb
settings noted. Record whether it appeared and any OS suppression. If no toast
appears, do not mark the native release gate as passed. This test does not
prove background, locked-screen, silent/DND, scheduled or closed-app delivery.

## Developer-only manual opt-in (after local Windows acceptance)

Install the worker in a virtual environment and launch
`orin-windows-reminders` in the signed-in user's session after setting:
`ORIN_WINDOWS_REMINDERS_ENABLED=1`,
`ORIN_WINDOWS_REMINDERS_API_URL=https://<trusted-api>`,
`ORIN_WINDOWS_REMINDERS_TOKEN=<short-lived-user-token>`,
`ORIN_WINDOWS_REMINDERS_OWNER_ID=<owner-uuid>`,
`ORIN_WINDOWS_REMINDERS_WORKSPACE_ID=<workspace-uuid>`,
`ORIN_WINDOWS_REMINDERS_BROWSER_SESSION_ID=<browser-auth-session-uuid>`,
`ORIN_WINDOWS_REMINDERS_BROWSER_LEASE_GENERATION=<current-browser-lease-generation-uuid>`,
`ORIN_WINDOWS_REMINDERS_APP_ID=<registered-AppUserModelID>`, and
`ORIN_WINDOWS_REMINDERS_SHORTCUT=<absolute-Start-Menu-Programs-lnk-path>`.
The shortcut must already exist in the current-user or all-users Start Menu
Programs directory and expose that exact AppUserModelID. Missing, mismatched,
or unregistered identity fails without marking any reminder as attempted.
Do not create or install a shortcut in a real user's Start Menu during automated tests; CI uses only a disposable runner profile.
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
