# Intelligent notifications and optional persistent follow-up

Orin runs deterministic notification rules in the API maintenance loop (every 15 seconds when BACKGROUND_WORKER_ENABLED=true). The browser refreshes the inbox/preferences every 30 seconds. Records, acknowledgement, snooze and repeat state survive process restarts. Delivery keys and unique database constraints suppress duplicate reminders across maintenance instances.

## Triggers

| Source | Trigger | Stops or invalidates follow-up |
|---|---|---|
| Calendar | Explicit event reminder offset, including timezone-aware all-day events | Event deleted, reminder removed, start/offset changed, acknowledgement |
| Routines | Explicit routine reminder offset and scheduled weekday | Paused/deleted/changed routine, check-in, acknowledgement |
| Tasks | 30 minutes before a real due date through a seven-day overdue catch-up window | Completion/cancellation, deleted task, changed/removed due date |
| Scheduled work | Ten minutes before a task block through one hour after start | Task completed/cancelled, block removed or rescheduled |
| Task review | Stored decay review time arrives, with seven-day catch-up | Completion/cancellation, changed review date |
| Projects/milestones | Target date reached in the notification timezone | Project inactive/deleted, milestone completed/deleted, date changed |
| Opportunities/risks | Explicit review date or opportunity deadline reached | Opportunity won/closed/deleted; risk resolved/deleted; date changed |
| Approvals | Pending decision, created within the last seven days | Decision, cancellation, expiry, deletion |
| Worker | Failed/expired job created within the last seven days | Record removed or no longer failed/expired |
| Writing | Failed analysis or saved note review date | Analysis no longer failed; note archived/deleted/review date changed |

Records are source-aware and deep-link to the relevant task/project or workspace. These reminders do not complete tasks or approve actions. Date-only reviews are eligible at midnight in the selected notification timezone. Calendar/routine interruption follow-up expires two hours after its reminder time; historical inbox records remain. Other sources use their lifecycle and explicit acknowledgement. Catch-up windows bound generation; they do not erase history. The inbox API has offset pagination and returns at most 200 rows per page; the current panel displays the latest 100.

## User controls

Settings → Notifications & follow-up enables/disables delivery and individual categories. Normal mode does not repeat. Quiet hours (including overnight intervals), a timezone and optional pauses during active Focus sessions govern interruption eligibility. Quiet-hour equality represents a full-day quiet period. Reminders still remain in the inbox during quiet/focus pauses; interruption alerts wait.

Stubborn mode is off by default and requires an explicit saved choice. It adds a prominent, non-modal follow-up banner and repeat revisions every 5/15/30/60 minutes. The user chooses 1–5 repeats per reminder (default 3). A shared database budget caps repeat revisions at eight per user-local day. Acknowledge, snooze (15/60 minutes in the inbox; 15 minutes/24 hours in the banner), completing the source, or Stop stubborn mode ends/defer follow-up. API snooze also supports five minutes. Snooze does not erase completion history or reset the repeat budget. The banner remains available for eligible unread items even after their audio repeat budget is exhausted.

Browser alerts and sound are separate opt-ins. Browser permission is requested only on a user click. Alerts are grouped into one generic preview per refresh; task/note text is not copied into OS previews. A short optional in-app tone is subject to audio availability and autoplay rules. Browser alerts are best effort and require a supported browser with Orin open. The browser caches delivered revisions for the session to reduce duplicate alerts.

## Platform delivery and limits

**Browser:** In-app banners, optional sound and browser notification previews remain
best-effort and require a supported browser with Orin open. They cannot override
device mute, silent mode, Do Not Disturb or OS notification permissions. This
release does not provide background web push, SMS, escalation calls or messages
to accountability contacts.

**Android (opt-in local OS scheduling):** The mobile app can schedule generic
local notifications through `expo-notifications` for the signed-in owner and
active workspace after explicit device permission and an enabled notification
channel. It plans at most 32 local alerts within the next seven days, refreshes
from authenticated task and inbox snapshots, and clears stale scoped schedules
on account/workspace changes or opt-out. It is not remote push delivery: new
tasks created while the app stays closed may not be scheduled until a successful
refresh. Device power, OS scheduling policy, channel settings and DND can delay
or suppress alerts. **Physical Android delivery has not been accepted on a
real device; no phone installation is authorized by this documentation.**

**Windows (experimental foreground companion):** An explicitly opted-in
foreground process can poll the authenticated API and attempt generic Windows
toasts for due tasks. It requires a matching registered Start Menu shortcut and
AppUserModelID, a current interactive user session, and valid owner/workspace
credentials. It is **not** a background service or auto-start installation.
The independently supplied token is not automatically revoked by browser
logout, so the companion must be stopped on account change. CI verifies
synthetic reminder logic and disposable shortcut registration, **not visible
delivery on the original Windows computer**. See
[Windows reminder acceptance](../apps/worker/WINDOWS_REMINDERS.md).

Neither native path guarantees sound or visibility through silent/DND modes,
a powered-off device, expired permissions or OS restrictions. Apple critical
alerts require an Apple-issued entitlement and user authorization; no such
entitlement or iOS critical-alert capability is claimed.

Official platform references:
- https://developer.apple.com/documentation/usernotifications/unauthorizationoptions/criticalalert
- https://developer.android.com/develop/ui/views/notifications
- https://learn.microsoft.com/en-us/windows/win32/shell/enable-desktop-toast-with-appusermodelid

## Operations and privacy

Use the production configuration, secrets and HTTPS guidance in operations.md. Run Alembic upgrade head for the new notification fields/preferences. Existing reminders retain history. Preferences/notifications use owner-scoped APIs and cascading account deletion, and account export includes them. The first settings record inherits the user's Focus timezone when available, otherwise UTC; users can edit it. This is a modular-monolith maintenance service, not an external delivery provider or a clinical intervention.
