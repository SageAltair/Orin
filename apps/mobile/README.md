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

**Notification delivery limitation:** These controls currently manage server-side reminder policy and the in-app inbox. The Android client does not yet request notification permission or schedule/post OS notifications. It cannot alert a user while closed, and cannot override silent mode or Do Not Disturb. Native delivery requires a compatible Expo notifications integration, explicit user consent, Android channel configuration, account/workspace isolation, and physical-device validation. Do not describe persistent follow-up as an OS-level guarantee.

**Dependency audit:** Expo's transitive build/config dependencies have an unresolved mobile audit baseline of 3 high and 5 low findings (2026-10-29). CI records a fresh mobile audit and rejects critical findings, increases above the known high count, or any high-severity package outside the currently observed `@expo/cli`, `expo`, and `zod`. This is a regression guard, not a declaration that existing high findings are safe. Review the uploaded audit artifact and upstream patches before release.


Desktop magazine notes are readable but intentionally not editable on mobile yet. This protects their rich layout from lossy conversion until the native block editor is implemented.

## Checks

```powershell
npm run typecheck
npm test
npm run export:android
```

`npm run export:android` verifies that Metro can produce the Android JavaScript bundle. A signed Play Store build will additionally require an Expo Application Services project or a generated native Android project and signing configuration.
