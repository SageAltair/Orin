import { useEffect, useState, useRef } from "react";
import { ActionIcon } from "./ActionIcon";
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
  const [filter, setFilter] = useState<"unread" | "all">("unread");
  const [error, setError] = useState("");
  const inboxGeneration = useRef(0);
  const policyGeneration = useRef(0);
  const [pendingActionId, setPendingActionId] = useState<string | null>(null);
  const actionInFlight = useRef(false);
  const centerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const refresh = (): Promise<void> => {
    const generation = ++inboxGeneration.current;
    return request<Reminder[]>("/notifications")
      .then((rows) => {
        if (generation !== inboxGeneration.current) return;
        setItems(Array.isArray(rows) ? rows : []);
        setError("");
      })
      .catch(() => {
        if (generation === inboxGeneration.current)
          setError("Reminders could not be refreshed.");
      });
  };
  useEffect(() => {
    void refresh();
    const preferences = () => {
      const generation = ++policyGeneration.current;
      return request<NotificationPolicy>("/notifications/preferences")
        .then((p) => {
          if (generation !== policyGeneration.current) return;
          if (p && typeof p.enabled === "boolean") setPolicy(p);
          void refresh();
        })
        .catch(() => undefined);
    };
    void preferences();
    window.addEventListener("orin-notification-preferences", preferences);
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        void preferences();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void preferences();
    }, 30000);
    return () => {
      inboxGeneration.current++;
      policyGeneration.current++;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("orin-notification-preferences", preferences);
    };
  }, []);
  const action = async (
    item: Reminder,
    kind: "acknowledge" | "snooze" | "read",
    minutes = 15,
  ) => {
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    setPendingActionId(item.id);
    setError("");
    try {
      if (kind === "read") {
        await request(`/notifications/${item.id}/read`, { method: "PATCH" });
      } else {
        await request(`/notifications/${item.id}/action`, {
          method: "POST",
          body: JSON.stringify({ action: kind, minutes }),
        });
      }
      await refresh();
    } catch {
      setError(kind === "read" ? "This reminder could not be marked read." : "Could not update this reminder. Try again.");
    } finally {
      actionInFlight.current = false;
      setPendingActionId(null);
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
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && !centerRef.current?.contains(event.target)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);
  const urgent = policy.persistent
    ? items.find((i) => i.attention_ready && !i.read_at)
    : undefined;
  const unread = items.filter((item) => !item.read_at).length;
  const visibleItems = filter === "unread" ? items.filter((item) => !item.read_at) : items;
  return (
    <div ref={centerRef} className="notification-center">
      <button
        ref={triggerRef}
        type="button"
        className="icon-button"
        aria-controls="orin-notification-panel"
        aria-label={unread ? `Reminders, ${unread} unread` : "Reminders"}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <ActionIcon name="bell" size={18} />
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
              disabled={pendingActionId !== null}
              onClick={() => void action(urgent, "snooze", 15)}
            >
              Snooze 15 min
            </button>
            <button
              className="secondary-button"
              disabled={pendingActionId !== null}
              onClick={() => void action(urgent, "acknowledge")}
            >
              Acknowledge
            </button>
            <button
              className="text-action"
              disabled={pendingActionId !== null}
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
        <section ref={panelRef} id="orin-notification-panel" className="notification-panel" aria-label="Your reminders">
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
              <ActionIcon name="close" size={16} />
            </button>
          </header>
          {error && (
            <p role="alert">
              {error} <button onClick={() => void refresh()}>Retry</button>
            </p>
          )}
          <div className="notification-panel-filters" role="group" aria-label="Filter reminders">
            <button type="button" aria-pressed={filter === "unread"} onClick={() => setFilter("unread")}>Unread ({unread})</button>
            <button type="button" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>All ({items.length})</button>
          </div>
          {items.length === 0 && !error && (
            <div className="notification-empty">
              <ActionIcon name="bell" size={24} />
              <p>No reminders yet.</p>
              <small>
                Calendar reminders arrive here, including while you're away.
              </small>
            </div>
          )}
          {items.length > 0 && visibleItems.length === 0 && !error && (
            <p className="notification-empty" role="status">All reminders have been read. Select All to review earlier reminders.</p>
          )}
          {visibleItems.map((item) => (
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
                    disabled={pendingActionId !== null}
                    onClick={() => void action(item, "snooze", 15)}
                  >
                    Snooze 15 min
                  </button>
                  <button
                    className="text-action"
                    disabled={pendingActionId !== null}
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
                  disabled={pendingActionId !== null}
                  onClick={() => void action(item, "read")}
                >
                  <ActionIcon name="check" size={14} /> Mark read
                </button>
              )}
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
