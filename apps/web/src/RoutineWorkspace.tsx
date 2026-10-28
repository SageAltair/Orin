import { useCallback, useEffect, useState, useRef } from "react";
import { ActionIcon } from "./ActionIcon";
import type { RoutineRecord, RoutineOccurrence } from "@orin/contracts";
import { ApiError, request } from "./api";
import { PlanningForm } from "./PlanningForm";
import "./planning.css";
const zoneNow = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
const localDay = (zone: string) =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const blank = (): Omit<RoutineRecord, "id"> => ({
  title: "",
  timezone: zoneNow(),
  weekdays: [0, 1, 2, 3, 4, 5, 6],
  start_date: localDay(zoneNow()),
  end_date: null,
  time_of_day: "09:00",
  duration_minutes: 15,
  minimum_minutes: 2,
  cue: "",
  steps: "",
  minimum_action: "",
  reward: "",
  reminder_minutes: null,
  paused: false,
});
export function RoutineWorkspace({
  start,
  end,
  selectedDay,
  timezone,
  onOccurrences,
}: {
  start: string;
  end: string;
  selectedDay: string;
  timezone: string;
  onOccurrences: (rows: RoutineOccurrence[]) => void;
}) {
  const [routines, setRoutines] = useState<RoutineRecord[]>([]);
  const [occurrences, setOccurrences] = useState<RoutineOccurrence[]>([]);
  const [draft, setDraft] = useState<ReturnType<typeof blank> | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [timer, setTimer] = useState<{ id: string; ends: number } | null>(null);
  const [now, setNow] = useState(Date.now());
  const generation = useRef(0);
  const refresh = useCallback(async () => {
    const currentGeneration = ++generation.current;
    const all: RoutineRecord[] = [];
    for (let offset = 0; ; offset += 200) {
      const rows = await request<RoutineRecord[]>(
        `/calendar/routines?offset=${offset}&limit=200`,
      );
      if (!Array.isArray(rows)) throw Error("Invalid routine response");
      all.push(...rows);
      if (rows.length < 200) break;
    }
    const rows = await request<RoutineOccurrence[]>(
      `/calendar/routine-occurrences?start=${start}&end=${end}&timezone=${encodeURIComponent(timezone)}`,
    );
    if (!Array.isArray(rows)) throw Error("Invalid occurrence response");
    if (currentGeneration !== generation.current) return;
    setRoutines(all);
    setOccurrences(rows);
    onOccurrences(rows);
  }, [start, end, timezone, onOccurrences]);
  useEffect(() => {
    let active = true;
    void refresh().catch(() => {
      if (active) setError("Routines could not be loaded. Try again.");
    });
    return () => {
      active = false;
      generation.current++;
    };
  }, [refresh]);
  useEffect(() => {
    if (!timer) return;
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, [timer]);
  const edit = (r: RoutineRecord) => {
    const { id, ...data } = r;
    setEditing(id);
    setDraft(data);
  };
  const checkin = async (
    o: RoutineOccurrence,
    status: RoutineOccurrence["status"],
  ) => {
    setBusy(o.routine_id);
    setError("");
    try {
      await request(
        `/calendar/routines/${o.routine_id}/checkins/${o.day}`,
        status === "pending"
          ? { method: "DELETE" }
          : { method: "PUT", body: JSON.stringify({ status }) },
      );
      await refresh();
      setNotice(
        status === "minimum"
          ? "Minimum version counts. You showed up."
          : status === "skipped"
            ? "A skip is information. Begin again at the next cue."
            : status === "done"
              ? "Done. Make room for a short break."
              : "Check-in reset.",
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not update routine.");
    } finally {
      setBusy(null);
    }
  };
  const selected = occurrences.filter(
    (o) =>
      new Intl.DateTimeFormat("en-CA", {
        timeZone: timezone,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).format(new Date(o.start_at)) === selectedDay,
  );
  return (
    <section className="routine-workspace" aria-label="Routines">
      <header className="planning-heading">
        <div>
          <span className="eyebrow">A RHYTHM, NOT A STREAK</span>
          <h2>Make starting easier</h2>
          <p>
            Use a cue, a small first step, and a lighter version for low-energy
            days.
          </p>
        </div>
        <button
          className="primary-button"
          onClick={() => {
            setEditing(null);
            setDraft({ ...blank(), timezone });
          }}
        >
          <ActionIcon name="add" size={16} /> New routine
        </button>
      </header>
      {error && (
        <p className="api-error" role="alert">
          {error}{" "}
          <button
            className="text-action"
            onClick={() =>
              void refresh()
                .then(() => setError(""))
                .catch(() => setError("Could not reload routines."))
            }
          >
            Retry
          </button>
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <div className="routine-day-heading">
        <h3>{selectedDay}</h3>
        <span>
          {
            selected.filter(
              (o) => o.status === "done" || o.status === "minimum",
            ).length
          }{" "}
          of {selected.length} checked in · no catch-up debt
        </span>
      </div>
      <div className="planning-list">
        {selected.map((o) => {
          const r = routines.find((r) => r.id === o.routine_id);
          const allowed = o.day <= localDay(r?.timezone || zoneNow());
          const seconds =
            timer?.id === o.routine_id
              ? Math.max(0, Math.ceil((timer.ends - now) / 1000))
              : null;
          return (
            <article key={o.routine_id}>
              <div className="planning-row-heading">
                <button className="planning-title" onClick={() => r && edit(r)}>
                  {o.title}
                </button>
                <span className="planning-badge">
                  {new Date(o.start_at).toLocaleTimeString([], {
                    hour: "numeric",
                    minute: "2-digit",
                    timeZone: r?.timezone,
                  })}{" "}
                  · {o.duration_minutes} min · {o.status}
                </span>
              </div>
              <p>
                {o.cue
                  ? `After ${o.cue}, begin.`
                  : "Choose a familiar cue to make the start visible."}
              </p>
              {r?.steps && (
                <details>
                  <summary>Your steps</summary>
                  <ol>
                    {r.steps
                      .split("\n")
                      .filter(Boolean)
                      .map((step, i) => (
                        <li key={i}>{step}</li>
                      ))}
                  </ol>
                </details>
              )}
              <p className="routine-minimum">
                <strong>Minimum version · {o.minimum_minutes} min</strong>{" "}
                {o.minimum_action || "Take the first small step."}
              </p>
              {r?.reward && <small>Afterwards: {r.reward}</small>}
              {seconds !== null && (
                <div className="routine-timer" role="timer">
                  {seconds > 0
                    ? `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`
                    : "Time is up. Pause, check in, or take a movement break."}
                  <button
                    className="text-action"
                    onClick={() => setTimer(null)}
                  >
                    Stop timer
                  </button>
                </div>
              )}
              <div className="planning-row-actions">
                {o.status === "pending" ? (
                  <>
                    <button
                      className="text-action"
                      onClick={() => {
                        setNow(Date.now());
                        setTimer({
                          id: o.routine_id,
                          ends: Date.now() + o.duration_minutes * 60000,
                        });
                      }}
                    >
                      <ActionIcon name="timer" size={15} /> Start timer
                    </button>
                    <button
                      className="secondary-button"
                      disabled={!allowed || busy === o.routine_id}
                      onClick={() => void checkin(o, "done")}
                    >
                      <ActionIcon name="check" size={15} /> Done
                    </button>
                    <button
                      className="text-action"
                      disabled={!allowed || busy === o.routine_id}
                      onClick={() => void checkin(o, "minimum")}
                    >
                      Minimum counts
                    </button>
                    <button
                      className="text-action"
                      disabled={!allowed || busy === o.routine_id}
                      onClick={() => void checkin(o, "skipped")}
                    >
                      Skip today
                    </button>
                  </>
                ) : (
                  <button
                    className="text-action"
                    disabled={busy === o.routine_id}
                    onClick={() => void checkin(o, "pending")}
                  >
                    <ActionIcon name="reset" size={14} /> Undo check-in
                  </button>
                )}
              </div>
            </article>
          );
        })}
        {!selected.length && (
          <div className="planning-empty">
            <ActionIcon name="timer" size={28} />
            <h3>A little structure, a little breathing room</h3>
            <p>
              No routines scheduled for this day. Begin with one repeatable
              action.
            </p>
          </div>
        )}
      </div>
      <details className="routine-library">
        <summary>Manage routines · {routines.length}</summary>
        {routines.map((r) => (
          <div className="routine-library-row" key={r.id}>
            <button className="text-action" onClick={() => edit(r)}>
              {r.title}
            </button>
            <small>
              {r.weekdays.map((d) => days[d]).join(" · ")} · {r.time_of_day} ·{" "}
              {r.paused ? "Paused" : r.timezone}
            </small>
            <button
              className="text-action"
              disabled={busy === r.id}
              onClick={async () => {
                setBusy(r.id);
                try {
                  const { id, ...data } = r;
                  await request(`/calendar/routines/${id}`, {
                    method: "PUT",
                    body: JSON.stringify({ ...data, paused: !r.paused }),
                  });
                  await refresh();
                } catch {
                  setError("Could not change routine.");
                } finally {
                  setBusy(null);
                }
              }}
            >
              {r.paused ? "Resume" : "Pause"}
            </button>
          </div>
        ))}
      </details>
      <p className="planning-footnote">
        Small steps, repeatable schedules, and breaks are informed by ADHD
        support guidance. These tools support planning; this app has not been
        clinically tested.
      </p>
      {draft && (
        <PlanningForm
          title={editing ? "Shape your routine" : "New routine"}
          onClose={() => setDraft(null)}
          onSave={async () => {
            await request(
              "/calendar/routines" + (editing ? `/${editing}` : ""),
              { method: editing ? "PUT" : "POST", body: JSON.stringify(draft) },
            );
            await refresh();
          }}
          onDelete={
            editing
              ? async () => {
                  await request(`/calendar/routines/${editing}`, {
                    method: "DELETE",
                  });
                  await refresh();
                }
              : undefined
          }
        >
          <label>
            Routine title
            <input
              required
              maxLength={240}
              value={draft.title}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            />
          </label>
          {!editing && (
            <button
              type="button"
              className="text-action"
              onClick={() =>
                setDraft({
                  ...draft,
                  title: "Gentle start",
                  cue: "my first glass of water",
                  steps:
                    "Clear one small space\nChoose today's first action\nOpen what I need",
                  minimum_action: "Open the thing I want to work on",
                  reward: "Stretch and take a breath",
                })
              }
            >
              Use a gentle-start template
            </button>
          )}
          <div
            className="routine-weekdays"
            role="group"
            aria-label="Repeat on weekdays"
          >
            {days.map((d, i) => (
              <label key={d}>
                <input
                  type="checkbox"
                  checked={draft.weekdays.includes(i)}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      weekdays: e.target.checked
                        ? [...draft.weekdays, i].sort()
                        : draft.weekdays.filter((x) => x !== i),
                    })
                  }
                />
                {d}
              </label>
            ))}
          </div>
          <div className="planning-form-grid">
            <label>
              Start date
              <input
                required
                type="date"
                value={draft.start_date}
                onChange={(e) =>
                  setDraft({ ...draft, start_date: e.target.value })
                }
              />
            </label>
            <label>
              End date (optional)
              <input
                type="date"
                min={draft.start_date}
                value={draft.end_date || ""}
                onChange={(e) =>
                  setDraft({ ...draft, end_date: e.target.value || null })
                }
              />
            </label>
            <label>
              At
              <input
                required
                type="time"
                value={draft.time_of_day}
                onChange={(e) =>
                  setDraft({ ...draft, time_of_day: e.target.value })
                }
              />
            </label>
            <label>
              Timezone
              <input
                required
                maxLength={64}
                value={draft.timezone}
                onChange={(e) =>
                  setDraft({ ...draft, timezone: e.target.value })
                }
              />
            </label>
            <label>
              Full minutes
              <input
                required
                type="number"
                min={1}
                max={240}
                value={draft.duration_minutes}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    duration_minutes: Number(e.target.value),
                  })
                }
              />
            </label>
            <label>
              Minimum minutes
              <input
                required
                type="number"
                min={1}
                max={draft.duration_minutes}
                value={draft.minimum_minutes}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    minimum_minutes: Number(e.target.value),
                  })
                }
              />
            </label>
          </div>
          <label>
            After this cue…
            <input
              maxLength={500}
              placeholder="my morning coffee"
              value={draft.cue}
              onChange={(e) => setDraft({ ...draft, cue: e.target.value })}
            />
          </label>
          <label>
            Steps, one per line
            <textarea
              maxLength={2000}
              placeholder="Open the document\nWrite one sentence"
              value={draft.steps}
              onChange={(e) => setDraft({ ...draft, steps: e.target.value })}
            />
          </label>
          <label>
            Minimum action
            <input
              maxLength={500}
              placeholder="Write one sentence"
              value={draft.minimum_action}
              onChange={(e) =>
                setDraft({ ...draft, minimum_action: e.target.value })
              }
            />
          </label>
          <label>
            Something to look forward to
            <input
              maxLength={500}
              placeholder="A stretch and my favourite song"
              value={draft.reward}
              onChange={(e) => setDraft({ ...draft, reward: e.target.value })}
            />
          </label>
          <label>
            In-app reminder
            <select
              value={draft.reminder_minutes ?? ""}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  reminder_minutes:
                    e.target.value === "" ? null : Number(e.target.value),
                })
              }
            >
              <option value="">Off</option>
              {[0, 5, 10, 15, 30].map((n) => (
                <option value={n} key={n}>
                  {n === 0 ? "At start" : `${n} minutes before`}
                </option>
              ))}
            </select>
          </label>
          <p className="planning-footnote">
            Editing changes the repeating schedule. Check-ins are kept by
            original date. Pausing hides occurrences and stops new reminders;
            resuming restores the schedule.
          </p>
        </PlanningForm>
      )}
    </section>
  );
}
