import { useEffect, useState } from "react";
import { Bell, Check, X } from "lucide-react";
import { request } from "./api";

type Reminder = {
  id: string;
  title: string;
  message: string;
  due_at: string;
  read_at: string | null;
};

export function NotificationCenter() {
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
    const timer = window.setInterval(() => void refresh(), 30000);
    return () => window.clearInterval(timer);
  }, []);
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
              <small>{new Date(item.due_at).toLocaleString()}</small>
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
