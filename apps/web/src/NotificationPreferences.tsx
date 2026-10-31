import { useEffect, useState, useRef } from "react";
import { request } from "./api";
import { getWindowsLeaseIdentifiers, isWindowsLeaseOptedIn, setWindowsLeaseOptIn, stopWindowsLease, windowsLeaseStatusEvent } from "./windowsReminderLease";
import {
  defaultNotificationPolicy,
  notificationCategories,
  playReminderSound,
  type NotificationPolicy,
} from "./notificationPolicy";
export function NotificationPreferencesPanel({ ownerId }: { ownerId?: string }) {
  const [policy, setPolicy] = useState<NotificationPolicy>({
    ...defaultNotificationPolicy,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [notice, setNotice] = useState("");
  const [recoveryRequired, setRecoveryRequired] = useState(false);
  const [windowsLeaseEnabled, setWindowsLeaseEnabled] = useState(() => isWindowsLeaseOptedIn(ownerId));
  useEffect(() => setWindowsLeaseEnabled(isWindowsLeaseOptedIn(ownerId)), [ownerId]);
  const [windowsLeaseIds, setWindowsLeaseIds] = useState(getWindowsLeaseIdentifiers);
  useEffect(() => {
    const update = () => setWindowsLeaseIds(getWindowsLeaseIdentifiers());
    window.addEventListener(windowsLeaseStatusEvent, update);
    return () => window.removeEventListener(windowsLeaseStatusEvent, update);
  }, []);
  const loadGeneration = useRef(0);
  const refresh = async (): Promise<void> => {
    const generation = ++loadGeneration.current;
    setLoading(true);
    setError("");
    try {
      let requiresRecovery = false;
      const p = await request<NotificationPolicy>(
        "/notifications/preferences",
        {},
        true,
        (response) => {
          requiresRecovery = response.headers.get("X-Orin-Preferences-Recovery") === "required";
        },
      );
      if (generation !== loadGeneration.current) return;
      if (!p || typeof p.enabled !== "boolean")
        throw Error("Invalid preferences");
      setPolicy(p);
      setRecoveryRequired(requiresRecovery);
      setLoaded(true);
    } catch {
      if (generation === loadGeneration.current)
        setError("Notification preferences could not be loaded.");
    } finally {
      if (generation === loadGeneration.current) setLoading(false);
    }
  };
  useEffect(() => {
    void refresh();
    return () => {
      loadGeneration.current++;
    };
  }, []);
  return (
    <section
      className="settings-section notification-preferences"
      aria-label="Notification preferences"
    >
      <h2>Notifications & follow-up</h2>
      <p>
        Useful prompts for your plans, with controls for when and how often they
        appear.
      </p>
      {error && (
        <p role="alert">
          {error}
          {!loaded && (
            <button className="text-action" onClick={() => void refresh()}>
              Retry
            </button>
          )}
        </p>
      )}
      {loading && <p role="status">Loading notification preferences…</p>}
      {recoveryRequired && !loading && (
        <p role="alert">
          Some saved notification settings could not be validated. Alerts are
          disabled for safety. Review your choices and save to repair them.
        </p>
      )}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            const saved = await request<NotificationPolicy>(
              "/notifications/preferences",
              { method: "PUT", body: JSON.stringify(policy) },
            );
            setPolicy(saved);
            setRecoveryRequired(false);
            setNotice("Notification preferences saved.");
            window.dispatchEvent(new Event("orin-notification-preferences"));
          } catch {
            setError(
              "Could not save these preferences. Your choices are still here.",
            );
          } finally {
            setBusy(false);
          }
        }}
      >
        <fieldset
          disabled={busy || loading || !loaded}
          style={{ border: 0, padding: 0 }}
        >
          <label>
            <input
              type="checkbox"
              checked={policy.enabled}
              onChange={(e) =>
                setPolicy({ ...policy, enabled: e.target.checked })
              }
            />{" "}
            Enable automatic notifications
          </label>
          <div className="notification-category-grid">
            {notificationCategories.map((category) => (
              <label key={category}>
                <input
                  type="checkbox"
                  checked={policy.categories.includes(category)}
                  onChange={(e) =>
                    setPolicy({
                      ...policy,
                      categories: e.target.checked
                        ? [...policy.categories, category]
                        : policy.categories.filter((c) => c !== category),
                    })
                  }
                />
                {category}
              </label>
            ))}
          </div>
          <label>
            <input
              type="checkbox"
              checked={policy.persistent}
              onChange={(e) =>
                setPolicy({ ...policy, persistent: e.target.checked })
              }
            />{" "}
            Enable stubborn mode (persistent follow-up)
          </label>
          <p>
            Opt in to a visible follow-up banner and repeated alerts until you
            acknowledge or snooze. Up to eight repeat alerts per day; completing
            the related work stops follow-up.
          </p>
          {policy.persistent && (
            <div className="planning-form-grid">
              <label>
                Repeat every
                <select
                  value={policy.repeat_minutes}
                  onChange={(e) =>
                    setPolicy({
                      ...policy,
                      repeat_minutes: Number(e.target.value),
                    })
                  }
                >
                  {[5, 15, 30, 60].map((n) => (
                    <option key={n} value={n}>
                      {n} minutes
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Maximum repeats per reminder
                <select
                  value={policy.max_repeats}
                  onChange={(e) =>
                    setPolicy({
                      ...policy,
                      max_repeats: Number(e.target.value),
                    })
                  }
                >
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n}>{n}</option>
                  ))}
                </select>
              </label>
            </div>
          )}
          <label>
            <input
              type="checkbox"
              checked={policy.quiet_enabled}
              onChange={(e) =>
                setPolicy({ ...policy, quiet_enabled: e.target.checked })
              }
            />{" "}
            Quiet hours
          </label>
          {policy.quiet_enabled && (
            <div className="planning-form-grid">
              <label>
                Quiet from
                <input
                  type="time"
                  value={policy.quiet_start}
                  onChange={(e) =>
                    setPolicy({ ...policy, quiet_start: e.target.value })
                  }
                />
              </label>
              <label>
                Until
                <input
                  type="time"
                  value={policy.quiet_end}
                  onChange={(e) =>
                    setPolicy({ ...policy, quiet_end: e.target.value })
                  }
                />
              </label>
            </div>
          )}
          <label>
            Notification timezone
            <input
              required
              value={policy.timezone}
              onChange={(e) =>
                setPolicy({ ...policy, timezone: e.target.value })
              }
            />
          </label>
          <label>
            <input
              type="checkbox"
              checked={policy.respect_focus}
              onChange={(e) =>
                setPolicy({ ...policy, respect_focus: e.target.checked })
              }
            />{" "}
            Pause interruption alerts during active Focus sessions
          </label>
          <label>
            <input
              type="checkbox"
              checked={policy.browser_alerts}
              onChange={(e) =>
                setPolicy({ ...policy, browser_alerts: e.target.checked })
              }
            />{" "}
            Browser alerts while Orin is open
          </label>
          <label>
            <input
              type="checkbox"
              checked={windowsLeaseEnabled}
              disabled={!ownerId}
              onChange={async (event) => {
                if (event.target.checked) {
                  setWindowsLeaseOptIn(true, ownerId);
                  setWindowsLeaseEnabled(true);
                  setNotice("Windows companion browser lease enabled for this tab.");
                } else {
                  try {
                    await stopWindowsLease();
                    setWindowsLeaseOptIn(false);
                    setWindowsLeaseEnabled(false);
                    setNotice("Windows companion browser lease disabled.");
                  } catch {
                    setError("Cannot disable the Windows lease until the server confirms revocation. Retry when online.");
                  }
                }
              }}
            />{" "}
            Authorize the Windows reminder companion while this browser tab is active
          </label>
          <p>
            Optional and off by default. The browser renews a short workspace-scoped
            lease; changing workspaces revokes the previous one. This does not install
            or start a Windows service. The companion still requires a separately
            authorized foreground launch and cannot promise closed-browser delivery.
          </p>
          {windowsLeaseEnabled && windowsLeaseIds && (
            <p>
              Browser session: <code>{windowsLeaseIds.sessionId}</code>
              {" "} Lease generation: <code>{windowsLeaseIds.generation}</code>.
              These identifiers are not access tokens. Use only with the matching
              workspace and a separately obtained short-lived companion token.
            </p>
          )}
          <button
            type="button"
            className="text-action"
            onClick={async () => {
              if (!("Notification" in window)) {
                setError("This browser does not support desktop alerts.");
                return;
              }
              const permission = await Notification.requestPermission();
              setNotice(
                permission === "granted"
                  ? "Browser permission granted. Enable and save browser alerts above."
                  : "Browser permission was not granted. In-app reminders still work.",
              );
            }}
          >
            Request browser permission
          </button>
          <label>
            <input
              type="checkbox"
              checked={policy.sound}
              onChange={(e) =>
                setPolicy({ ...policy, sound: e.target.checked })
              }
            />{" "}
            Optional in-app sound (use Test sound once in this tab)
          </label>
          <button
            type="button"
            className="text-action"
            onClick={() =>
              void playReminderSound()
                .then(() =>
                  setNotice("Sound test played if your device allows audio."),
                )
                .catch(() =>
                  setError("Audio is unavailable or blocked by your browser."),
                )
            }
          >
            Test sound
          </button>
          <p>
            Web alerts and sound need Orin open and remain subject to
            browser/device settings. Silent mode and Do Not Disturb cannot be
            overridden here. Background push and native critical alerts are not
            configured.
          </p>
          <button
            className="primary-button"
            disabled={busy || loading || !loaded}
          >
            {busy ? "Saving…" : "Save notification preferences"}
          </button>
        </fieldset>
      </form>
      {notice && <p role="status">{notice}</p>}
    </section>
  );
}
