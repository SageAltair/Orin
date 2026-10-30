# Orin for Android

This is Orin's native Expo/React Native client. It uses the existing FastAPI service and does not duplicate backend state or business logic.

## Run on the Android emulator

1. Start Orin's database and API from the repository root:

   ```powershell
   docker compose up -d db api
   ```

2. Start an Android Virtual Device in Android Studio.
3. From `apps/mobile`, install and launch:

   ```powershell
   npm install
   npm run android
   ```

In development, the app defaults to `http://10.0.2.2:8100`, the Android emulator route to the host machine. For a physical Android device, create `.env.local` and use the computer's LAN address:

```dotenv
EXPO_PUBLIC_API_BASE_URL=http://192.168.1.20:8100
```

The phone and computer must be on the same trusted network and the API port must be reachable. Production builds require an HTTPS `EXPO_PUBLIC_API_BASE_URL`; the client intentionally rejects plain HTTP outside development.

### Troubleshooting physical-device login

1. On Windows, run `ipconfig` and find the active Wi-Fi adapter's IPv4 address. Use that address, not `127.0.0.1`, `172.0.0.1`, or `10.0.2.2` (the last one is for Android emulators only).
2. Confirm `http://<WINDOWS_LAN_IP>:8100/health/ready` responds from the phone's browser while both devices are on the same trusted network. If it does not, check the API binding, Docker port mapping, Windows Firewall, and Wi-Fi client isolation before debugging passwords.
3. For a **development build**, set `EXPO_PUBLIC_API_BASE_URL=http://<WINDOWS_LAN_IP>:8100` in `apps/mobile/.env.local`, then restart Expo and rebuild the Android client so its configuration is included.
4. For a **release APK**, use a reachable HTTPS API origin with a valid certificate. A production build will not accept a LAN HTTP origin; an APK built with an incorrect endpoint cannot be repaired by changing the computer's IP alone.
5. An expired access token requires a working refresh cookie. A temporary offline or server failure now preserves locally stored credentials, but the app still needs a reachable API to authenticate.

Do not expose the development API directly to the public internet or disable Android transport security to work around a bad URL.

## Current mobile surface

- Sign in and registration with encrypted OS-backed access-token storage.
- Workspace selection and creation, with workspace-scoped tasks and projects.
- Home overview and the existing approval-aware Orin command API.
- Task capture and completion.
- Project creation and project summaries.
- Writing list and plain-note editing.
- Calendar event creation, deletion and 30-day agenda.
- Notification inbox, acknowledgement, snooze and follow-up preferences.

- Approval review with explicit approve/deny controls.
- Activity and execution audit trail.
- Focus-session start, pause, resume, completion and cancellation.
- Daily routines with upcoming occurrences and done/minimum/skipped check-ins.
- Opportunity and risk capture, including conversion of next actions into tasks.
- Global search across tasks, projects, writing and Orin conversations.
- Structured personal memories with explicit provenance and archive controls.
- Synced interface, autonomy and proactive-assistance preferences.
- Account security with session review/revocation and password rotation.
- Automatic light/dark appearance.

**Notification delivery limitation:** Server-side reminder policy and the in-app inbox are available. The Android client additionally supports explicit opt-in, best-effort local OS scheduling of already-known reminders and future task deadlines. This is not server push delivery: newly created or changed remote reminders cannot update a closed app, Android may suppress alerts, and silent mode or Do Not Disturb cannot be bypassed. Physical-device acceptance remains unverified. See **Android device reminders** below; do not describe persistent follow-up as guaranteed OS-level delivery.

**Dependency audit:** Expo's transitive build/config dependencies have an unresolved mobile audit baseline of 3 high and 5 low findings (2026-10-29). CI records a fresh mobile audit and rejects critical findings, increases above the known high count, any high-severity package outside the currently observed `@expo/cli`, `expo`, and `zod`, or any changed high-severity advisory identity outside the reviewed `GHSA-mrhx-c7xc-m3w5` transitive chain. Missing or circular advisory data fails closed. This is a regression guard, not a declaration that existing high findings are safe. Review the uploaded audit artifact and upstream patches before release.


Desktop magazine notes are readable but intentionally not editable on mobile yet. This protects their rich layout from lossy conversion until the native block editor is implemented.

## Checks

```powershell
npm run typecheck
npm test
npm run export:android
```

`npm run export:android` verifies that Metro can produce the Android JavaScript bundle. A signed Play Store build will additionally require an Expo Application Services project or a generated native Android project and signing configuration.


## Mobile Tasks planning

The mobile Tasks screen now opens on **All**, loads every owner/workspace-scoped task page instead of silently stopping at 100, and offers Today, Upcoming, Overdue, Completed and text search. Quick creation and editing accept an optional local due date and time in `YYYY-MM-DDTHH:MM` format. Orin converts it to UTC, rejects nonexistent or ambiguous daylight-saving clock times, and preserves an existing exact instant when unrelated fields are edited. Due timestamps appear with local date and time. Network/pagination failures do not replace previously loaded tasks. This is a text-entry date/time control, not a native calendar picker.

## Android device reminders (local, opt-in)

The Notifications screen offers a separate **Device reminders** opt-in. Permission is requested only when enabled. Orin schedules a capped set of known future task deadlines (up to seven days ahead) and unread, category-allowed inbox reminders using Expo Notifications' best-effort Android date triggers, without exact-alarm or Do Not Disturb bypass permissions. Notification tray text is generic to avoid exposing task details on a lock screen. Opening Orin, returning it to the foreground, editing tasks in the mobile Tasks screen, or reopening the inbox reconciles known future task deadlines, revisions, acknowledgements, snoozes and policy changes. The planner deduplicates a task deadline when its matching server reminder appears. A complete paginated owner/workspace-scoped task fetch must succeed before replacing device schedules; fetch failures preserve existing alerts. Explicit logout and account switching cancel Orin-owned scheduled and presented notifications and clear the account-specific opt-in. An offline session-restore failure does not count as logout and does not erase previously opted-in local schedules.

**Important limitations:** No push token is registered and no server-to-device push delivery exists. Tasks known at the last successful sync can alert at their due times while Orin is closed, within the seven-day/32-item scheduling window. Tasks more than seven days away, changes/completions made on other devices while Orin stays closed, and new server reminders cannot be scheduled or cancelled until Orin reconnects. Known future reminders falling inside quiet hours are deferred to the next allowed local time, including across daylight-saving changes, provided the deferred time remains inside the seven-day scheduling window; all-day quiet hours suppress scheduling. Generic alerts sharing the same scheduled instant are coalesced into one device notification to avoid a burst when quiet hours end; open Orin to review all pending items. Switching workspaces reconciles the active workspace's task schedule. Android can delay or suppress alerts under battery, permission, silent mode or DND policies. Local scheduling cannot re-check future focus sessions after the app closes. This is not an always-on reminder guarantee. Physical-device delivery is not verified; do not describe it as release-ready until emulator/device acceptance is complete. To run tests: `npm test --prefix apps/mobile` and `npm run typecheck --prefix apps/mobile` from the repository root.
