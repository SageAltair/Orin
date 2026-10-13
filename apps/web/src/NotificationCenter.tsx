import { useEffect, useState } from "react";
import { Bell, Check, X } from "lucide-react";
import {
  defaultNotificationPolicy,
  playReminderSound,
  type NotificationPolicy,
} from "./notificationPolicy";
import "./notifications.css";
import { request } from "./api";

type Reminder = {
  id: string;
  title: string;
  message: string;
  due_at: string;
  read_at: string | null;
  category: string;
  source_id: string | null;
  snoozed_until: string | null;
  revision: number;
  repeats: number;
  attention_ready: boolean;
};

export function NotificationCenter({
  onOpen,
}: {
  onOpen?: (category: string, id: string | null) => void;
}) {
  const [policy, setPolicy] = useState<NotificationPolicy>(
    defaultNotificationPolicy,
  );
  const [items, setItems] = useState<Reminder[]>([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const refresh = () =>
    request<Reminder[]>("/notifications")
      .then((rows) => {
        setItems(Array.isArray(rows) ? rows : []);
        setError("");
      })
      .catch(() => setError("Reminders could not be refreshed."));
  useEffect(() => {
    void refresh();
    const preferences = () =>
      request<NotificationPolicy>("/notifications/preferences")
        .then((p) => {
          if (p && typeof p.enabled === "boolean") setPolicy(p);
          void refresh();
        })
        .catch(() => undefined);
    void preferences();
    window.addEventListener("orin-notification-preferences", preferences);
    const timer = window.setInterval(() => {
      void preferences();
      void refresh();
    }, 30000);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("orin-notification-preferences", preferences);
    };
  }, []);
  const action = async (
    item: Reminder,
    kind: "acknowledge" | "snooze",
    minutes = 15,
  ) => {
    try {
      await request(`/notifications/${item.id}/action`, {
        method: "POST",
        body: JSON.stringify({ action: kind, minutes }),
      });
      await refresh();
    } catch {
      setError("Could not update this reminder. Try again.");
    }
  };
  useEffect(() => {
    if (!policy.browser_alerts && !policy.sound) return;
    const pending = items
      .filter((i) => i.attention_ready && !i.read_at)
      .filter((i) => {
        try {
          return !sessionStorage.getItem(`orin:alert:${i.id}:${i.revision}`);
        } catch {
          return false;
        }
      });
    if (!pending.length) return;
    if (
      policy.browser_alerts &&
      "Notification" in window &&
      Notification.permission === "granted"
    ) {
      try {
        const alert = new Notification("Orin reminders", {
          body: `${pending.length} new or repeated reminder${pending.length === 1 ? "" : "s"} in your workspace.`,
          tag: "orin-reminder-digest",
        });
        alert.onclick = () => {
          window.focus();
          setOpen(true);
          alert.close();
        };
      } catch {
        /* Some browsers require service-worker delivery. */
      }
    }
    if (policy.sound) void playReminderSound().catch(() => undefined);
    for (const item of pending) {
      try {
        sessionStorage.setItem(
          `orin:alert:${item.id}:${item.revision}`,
          "seen",
        );
      } catch {
        /* Inbox remains available. */
      }
    }
  }, [items, policy.browser_alerts, policy.sound]);
  const urgent = policy.persistent
    ? items.find((i) => i.attention_ready && !i.read_at)
    : undefined;
  const unread = items.filter((item) => !item.read_at).length;
  return (
    <div className="notification-center">
      <button
        type="button"
        className="icon-button"
        aria-label={unread ? `Reminders, ${unread} unread` : "Reminders"}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <Bell size={18} />
        {unread > 0 && <span className="notification-dot" />}
      </button>
      {urgent && (
        <aside
          className="notification-followup"
          aria-label="Persistent follow-up"
        >
          {error && <p role="alert">{error}</p>}
          <div>
            <strong>{urgent.title}</strong>
            <p>{urgent.message}</p>
            <small>
              {urgent.repeats
                ? `Follow-up ${urgent.repeats} of ${policy.max_repeats}`
                : "A small next step can be enough."}
            </small>
          </div>
          <div>
            <button
              className="text-action"
              onClick={() => {
                onOpen?.(urgent.category, urgent.source_id);
                setOpen(true);
              }}
            >
              Open
            </button>
            <button
              className="text-action"
              onClick={() => void action(urgent, "snooze", 15)}
            >
              Snooze 15 min
            </button>
            <button
              className="secondary-button"
              onClick={() => void action(urgent, "acknowledge")}
            >
              Acknowledge
            </button>
            <button
              className="text-action"
              onClick={() => void action(urgent, "snooze", 1440)}
            >
              Snooze 24 hours
            </button>
            <button
              className="text-action"
              onClick={async () => {
                try {
                  const updated = await request<NotificationPolicy>(
                    "/notifications/preferences",
                    {
                      method: "PUT",
                      body: JSON.stringify({ ...policy, persistent: false }),
                    },
                  );
                  setPolicy(updated);
                  window.dispatchEvent(
                    new Event("orin-notification-preferences"),
                  );
                } catch {
                  setError(
                    "Could not stop follow-up. Try again in notification settings.",
                  );
                }
              }}
            >
              Stop stubborn mode
            </button>
          </div>
        </aside>
      )}
      {open && (
        <section className="notification-panel" aria-label="Your reminders">
          <header>
            <div>
              <strong>Reminders</strong>
              <small>{unread ? `${unread} unread` : "You're caught up"}</small>
            </div>
            <button
              className="icon-button"
              aria-label="Close reminders"
              onClick={() => setOpen(false)}
            >
              <X size={16} />
            </button>
          </header>
          {error && (
            <p role="alert">
              {error} <button onClick={() => void refresh()}>Retry</button>
            </p>
          )}
          {items.length === 0 && !error && (
            <div className="notification-empty">
              <Bell size={24} />
              <p>No reminders yet.</p>
              <small>
                Calendar reminders arrive here, including while you're away.
              </small>
            </div>
          )}
          {items.map((item) => (
            <article key={item.id} className={item.read_at ? "is-read" : ""}>
              <strong>{item.title}</strong>
              <p>{item.message}</p>
              <small>
                {item.category} · {new Date(item.due_at).toLocaleString()}
                {item.snoozed_until
                  ? ` · Snoozed until ${new Date(item.snoozed_until).toLocaleString()}`
                  : ""}
              </small>
              {item.source_id && (
                <button
                  className="text-action"
                  onClick={() => {
                    onOpen?.(item.category, item.source_id);
                    setOpen(false);
                  }}
                >
                  Open related item
                </button>
              )}
              {!item.read_at && (
                <>
                  <button
                    className="text-action"
                    onClick={() => void action(item, "snooze", 15)}
                  >
                    Snooze 15 min
                  </button>
                  <button
                    className="text-action"
                    onClick={() => void action(item, "snooze", 60)}
                  >
                    Snooze 1 hour
                  </button>
                </>
              )}
              {!item.read_at && (
                <button
                  className="text-action"
                  aria-label={`Mark ${item.title} read`}
                  onClick={async () => {
                    try {
                      await request(`/notifications/${item.id}/read`, {
                        method: "PATCH",
                      });
                      await refresh();
                    } catch {
                      setError("This reminder could not be marked read.");
                    }
                  }}
                >
                  <Check size={14} /> Mark read
                </button>
              )}
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
