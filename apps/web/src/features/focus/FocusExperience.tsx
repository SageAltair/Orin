import { useEffect, useMemo, useState } from "react";
import { Command, Plus, X } from "lucide-react";
import { request } from "../../api";
import { Capture } from "./Capture";
import { Close } from "./Close";
import { Later } from "./Later";
import { Now } from "./Now";
import { TodaysThree } from "./TodaysThree";
import { useFocusWorkspace } from "./useFocusWorkspace";
import type { CaptureSuggestion, FocusTask } from "./types";

type Surface = "now" | "today" | "capture" | "close" | "later" | "settings";
type Theme = "light" | "dark" | "auto";
type Settings = { theme: Theme; reduced_motion: boolean; hide_timer_numbers: boolean; sound_enabled: boolean; haptics_enabled: boolean };

function readStored<T>(key: string, fallback: T): T {
  try { const value = localStorage.getItem(key); return value ? JSON.parse(value) as T : fallback; }
  catch { return fallback; }
}

export function FocusExperience({ name, onSignOut, embedded = false }: { name: string; onSignOut: () => void; embedded?: boolean }) {
  const focus = useFocusWorkspace();
  const [surface, setSurface] = useState<Surface>("now");
  const [captureMessage, setCaptureMessage] = useState("");
  const [theme, setTheme] = useState<Theme>(() => readStored("orin.focus.theme.v1", "auto"));
  const [reducedMotion, setReducedMotion] = useState(() => readStored("orin.focus.reduced-motion.v1", false));
  const [hideTimerNumbers, setHideTimerNumbers] = useState(() => readStored("orin.focus.hide-timer.v1", false));
  const [soundEnabled, setSoundEnabled] = useState(() => readStored("orin.focus.sound.v1", false));
  const [hapticsEnabled, setHapticsEnabled] = useState(() => readStored("orin.focus.haptics.v1", false));
  const [systemDark, setSystemDark] = useState(false);
  const [systemReducedMotion, setSystemReducedMotion] = useState(false);
  const [closeMessage, setCloseMessage] = useState("");
  const [laterOverride, setLaterOverride] = useState<FocusTask | null>(null);
  const dark = theme === "dark" || (theme === "auto" && systemDark);
  const reduce = reducedMotion || systemReducedMotion;

  useEffect(() => {
    const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updateDark = () => setSystemDark(darkQuery.matches);
    const updateMotion = () => setSystemReducedMotion(motionQuery.matches);
    updateDark(); updateMotion(); darkQuery.addEventListener("change", updateDark); motionQuery.addEventListener("change", updateMotion);
    return () => { darkQuery.removeEventListener("change", updateDark); motionQuery.removeEventListener("change", updateMotion); };
  }, []);

  useEffect(() => {
    void request<Settings>("/focus/settings").then(settings => {
      setTheme(settings.theme); setReducedMotion(settings.reduced_motion); setHideTimerNumbers(settings.hide_timer_numbers);
      setSoundEnabled(settings.sound_enabled); setHapticsEnabled(settings.haptics_enabled);
    }).catch(() => undefined);
  }, []);

  useEffect(() => { document.documentElement.dataset.focusTheme = dark ? "dark" : "light"; }, [dark]);
  useEffect(() => {
    localStorage.setItem("orin.focus.theme.v1", JSON.stringify(theme));
    localStorage.setItem("orin.focus.reduced-motion.v1", JSON.stringify(reducedMotion));
    localStorage.setItem("orin.focus.hide-timer.v1", JSON.stringify(hideTimerNumbers));
    localStorage.setItem("orin.focus.sound.v1", JSON.stringify(soundEnabled));
    localStorage.setItem("orin.focus.haptics.v1", JSON.stringify(hapticsEnabled));
  }, [theme, reducedMotion, hideTimerNumbers, soundEnabled, hapticsEnabled]);

  const nav = useMemo(() => [
    { id: "now" as const, label: "Now" }, { id: "today" as const, label: "Today" },
    { id: "capture" as const, label: "Capture" }, { id: "close" as const, label: "Close" },
  ], []);
  const saveSettings = async (patch: Record<string, unknown>) => {
    try { await request("/focus/settings", { method: "PUT", body: JSON.stringify(patch) }); }
    catch { /* Browser preferences still work if settings sync is temporarily unavailable. */ }
  };
  const setThemeValue = (value: Theme) => { setTheme(value); void saveSettings({ theme: value }); };
  const setMotionValue = (value: boolean) => { setReducedMotion(value); void saveSettings({ reduced_motion: value }); };
  const setTimerNumbersValue = (value: boolean) => { setHideTimerNumbers(value); void saveSettings({ hide_timer_numbers: value }); };
  const setSoundValue = (value: boolean) => { setSoundEnabled(value); void saveSettings({ sound_enabled: value }); };
  const setHapticsValue = (value: boolean) => { setHapticsEnabled(value); void saveSettings({ haptics_enabled: value }); };

  const capture = async (title: string, details: { first_step?: string; energy_level?: "low" | "medium" | "high" }) => {
    setCaptureMessage("");
    const task = await focus.capture(title, details);
    if (task) setCaptureMessage("Saved to Inbox.");
    return task;
  };
  const suggestCapture = (title: string) => request<CaptureSuggestion>("/focus/capture/suggest", { method: "POST", body: JSON.stringify({ title }) });
  const addLaterToToday = (task: FocusTask) => {
    const current = focus.today?.tasks ?? [];
    if (current.length >= 3) { setLaterOverride(task); setSurface("today"); return; }
    const items = current.map(item => ({ task_id: item.id, is_anchor: item.is_anchor ?? false }));
    items.push({ task_id: task.id, is_anchor: current.length === 0 });
    void focus.replaceToday(items); setSurface("now");
  };
  const navClick = (next: Surface) => { setSurface(next); setCaptureMessage(""); setCloseMessage(""); setLaterOverride(null); };

  return <div className={`focus-shell ${embedded ? "focus-embedded" : ""} ${dark ? "focus-dark" : "focus-light"} ${reduce ? "focus-reduced-motion" : ""}`}>
    <a className="focus-skip" href="#focus-main">Skip to content</a>
    {!embedded && <header className="focus-header"><div className="focus-brand"><span className="focus-brand-mark"><Command size={17} /></span><span>orin</span></div><span className="focus-greeting">Here with you, {name.split(" ")[0]}</span><button className="focus-signout" type="button" aria-label="Sign out" onClick={onSignOut}><X size={18} /></button></header>}
    <main id="focus-main" className="focus-main" tabIndex={-1}>
      {focus.error && <p className="focus-error" role="alert">{focus.error}</p>}
      {surface === "now" && <Now state={focus.now} busy={focus.busy} onStart={() => void focus.start()} onComplete={() => void focus.complete()} onSmaller={async step => { if (focus.now?.task) await focus.saveFirstStep(focus.now.task, step); }} onSuggestSmaller={() => focus.now?.task ? focus.suggestSmallerStep(focus.now.task) : Promise.resolve(null)} onSwap={focus.swap} onCapture={() => navClick("capture")} onChooseEnergy={() => navClick("today")} reducedMotion={reduce} hideNumbers={hideTimerNumbers} />}
      {surface === "today" && !laterOverride && <TodaysThree plan={focus.today} later={focus.later} onEnergy={energy => void focus.chooseEnergy(energy)} onReplace={items => void focus.replaceToday(items)} onOpenLater={() => navClick("later")} onSettings={() => navClick("settings")} onSkipEnergy={() => navClick("now")} />}
      {surface === "today" && laterOverride && <section className="focus-card"><button className="focus-text-button" onClick={() => setLaterOverride(null)}>Back to Today</button><h1>Choose where it fits.</h1>{(focus.today?.tasks ?? []).map(task => <button key={task.id} className="focus-choose-row" onClick={() => { const items = (focus.today?.tasks ?? []).map(item => ({ task_id: item.id === task.id ? laterOverride.id : item.id, is_anchor: item.is_anchor ?? false })); void focus.replaceToday(items); setLaterOverride(null); }}>{task.is_anchor ? "Replace anchor" : `Replace ${task.title}`}</button>)}</section>}
      {surface === "capture" && <><Capture onSave={capture} onSuggest={suggestCapture} busy={focus.busy} onDone={() => { window.setTimeout(() => navClick("now"), 500); }} />{captureMessage && <p className="focus-quiet-message" role="status">{captureMessage}</p>}</>}
      {surface === "close" && <>{closeMessage ? <section className="focus-card"><span className="focus-eyebrow">CLOSED</span><h1>That was enough for today.</h1><p>You can begin again whenever you return.</p><button className="focus-primary" onClick={() => navClick("now")}>Back to Now</button></section> : <Close value={focus.close} later={focus.later} busy={focus.busy} onSave={async input => { if (await focus.saveClose(input)) setCloseMessage("saved"); }} onSkip={() => navClick("now")} />}</>}
      {surface === "later" && <Later tasks={focus.later} onBack={() => navClick("today")} onChoose={addLaterToToday} />}
      {surface === "settings" && <section className="focus-card focus-settings-page"><button className="focus-text-button" onClick={() => navClick("today")}>Back to Today</button><span className="focus-eyebrow">PREFERENCES</span><h1>Make it comfortable.</h1><label>Theme<select value={theme} onChange={event => setThemeValue(event.target.value as Theme)}><option value="auto">Auto</option><option value="light">Light</option><option value="dark">Dark</option></select></label><label className="focus-toggle"><input type="checkbox" checked={reducedMotion} onChange={event => setMotionValue(event.target.checked)} /> Reduce motion</label><label className="focus-toggle"><input type="checkbox" checked={hideTimerNumbers} onChange={event => setTimerNumbersValue(event.target.checked)} /> Hide timer numbers</label><label className="focus-toggle"><input type="checkbox" checked={soundEnabled} onChange={event => setSoundValue(event.target.checked)} /> Sound (off by default)</label><label className="focus-toggle"><input type="checkbox" checked={hapticsEnabled} onChange={event => setHapticsValue(event.target.checked)} /> Light haptics</label><p className="focus-quiet-message">Reminders cannot be delivered yet. They are not being sent.</p><p className="focus-quiet-message">Orin supports focus and is not a medical treatment.</p></section>}
    </main>
    <button type="button" className="focus-fab" aria-label="Capture a task" onClick={() => navClick("capture")}><Plus size={23} /><span>Capture</span></button>
    <nav className="focus-bottom-nav" aria-label="Focus navigation">{nav.map(item => <button type="button" key={item.id} className={surface === item.id ? "active" : ""} aria-current={surface === item.id ? "page" : undefined} onClick={() => navClick(item.id)}>{item.label}</button>)}</nav>
  </div>;
}
