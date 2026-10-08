import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ArrowUpRight, Command, Menu, Moon, Pin, Plus, Send, Settings2, Sun } from "lucide-react";
import { capabilities, defaultPreferences, getNavigationCapabilities, normalizePreferences, type CapabilityId, type UserPreferences } from "./capabilities";

const storageKey = "orin.preferences.v1";
type Page = CapabilityId;

function readPreferences(): UserPreferences {
  try {
    const saved = localStorage.getItem(storageKey);
    return saved ? normalizePreferences(JSON.parse(saved) as unknown) : defaultPreferences;
  } catch { return defaultPreferences; }
}

function EmptyState({ title, detail, action }: { title: string; detail: string; action?: string }) {
  return <div className="empty-state"><span className="empty-mark" aria-hidden="true">○</span><h3>{title}</h3><p>{detail}</p>{action && <button className="text-button" type="button" disabled><Plus size={15} />{action}<span className="soon">Not available yet</span></button>}</div>;
}

function PreferenceSettings({ preferences, onChange }: { preferences: UserPreferences; onChange: (value: UserPreferences) => void }) {
  const toggleCapability = (id: CapabilityId) => {
    const visible = preferences.visibleCapabilities.includes(id);
    const next = visible ? preferences.visibleCapabilities.filter((item) => item !== id) : [...preferences.visibleCapabilities, id];
    onChange({ ...preferences, visibleCapabilities: next, hiddenCapabilities: capabilities.map((item) => item.id).filter((item) => !next.includes(item)), pinnedCapabilities: preferences.pinnedCapabilities.filter((item) => next.includes(item)) });
  };
  const togglePin = (id: CapabilityId) => onChange({ ...preferences, pinnedCapabilities: preferences.pinnedCapabilities.includes(id) ? preferences.pinnedCapabilities.filter((item) => item !== id) : [...preferences.pinnedCapabilities, id] });
  return <div className="settings-content">
    <section className="settings-section"><div className="section-heading"><div><span className="eyebrow">YOUR WORKSPACE</span><h2>Choose what you see</h2></div><p>Keep navigation focused on the capabilities you use.</p></div>
      <div className="capability-list">{capabilities.filter((item) => item.id !== "settings").map((item) => {
        const visible = preferences.visibleCapabilities.includes(item.id);
        return <div className="capability-row" key={item.id}><span className="capability-glyph" aria-hidden="true">{item.icon}</span><div className="capability-info"><strong>{item.label}</strong><span>{item.description}</span></div><button className={`pin-button ${preferences.pinnedCapabilities.includes(item.id) ? "is-pinned" : ""}`} aria-label={`${preferences.pinnedCapabilities.includes(item.id) ? "Unpin" : "Pin"} ${item.label}`} title="Pin in navigation" onClick={() => togglePin(item.id)} disabled={!visible}><Pin size={15} /></button><label className="switch-label"><span className="sr-only">Show {item.label} in navigation</span><input type="checkbox" checked={visible} onChange={() => toggleCapability(item.id)} /><span className="switch" /></label></div>;
      })}</div>
    </section>
    <section className="settings-section"><div className="section-heading"><div><span className="eyebrow">APPEARANCE</span><h2>Make it yours</h2></div><p>Your preferences are saved on this device.</p></div>
      <div className="preference-controls"><label>Interface density<select value={preferences.density} onChange={(event) => onChange({ ...preferences, density: event.target.value as UserPreferences["density"] })}><option value="comfortable">Comfortable</option><option value="compact">Compact</option></select></label><label>Theme<select value={preferences.theme} onChange={(event) => onChange({ ...preferences, theme: event.target.value as UserPreferences["theme"] })}><option value="light">Light</option><option value="dark">Dark</option><option value="system">System</option></select></label></div>
    </section>
  </div>;
}

export default function App() {
  const [preferences, setPreferences] = useState<UserPreferences>(readPreferences);
  const [page, setPage] = useState<Page>("home");
  const [command, setCommand] = useState("");
  const [commandMessage, setCommandMessage] = useState("");
  const [mobileOpen, setMobileOpen] = useState(false);
  const navigation = useMemo(() => getNavigationCapabilities(capabilities, preferences), [preferences]);

  useEffect(() => { localStorage.setItem(storageKey, JSON.stringify(preferences)); }, [preferences]);
  useEffect(() => { if (page !== "settings" && !preferences.visibleCapabilities.includes(page)) setPage("home"); }, [page, preferences.visibleCapabilities]);

  const submitCommand = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!command.trim()) return;
    setCommandMessage("Ask Orin is not connected yet. Your request has not been sent or acted on.");
    setCommand("");
  };
  const selectPage = (id: Page) => { setPage(id); setMobileOpen(false); };
  const title = page[0].toUpperCase() + page.slice(1);

  return <div className={`orin-shell density-${preferences.density} theme-${preferences.theme}`}>
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className={`sidebar ${mobileOpen ? "mobile-open" : ""}`} aria-label="Main navigation">
      <a className="brand" href="#home" onClick={(event) => { event.preventDefault(); selectPage("home"); }}><span className="brand-mark"><Command size={17} /></span><span>orin</span></a>
      <div className="workspace-switch"><span className="workspace-avatar">M</span><span><strong>My workspace</strong><small>Personal</small></span><span className="chevron">⌄</span></div>
      <span className="nav-label">WORKSPACE</span>
      <nav className="navigation">{navigation.map((item) => <button key={item.id} type="button" className={`nav-link ${page === item.id ? "active" : ""}`} onClick={() => selectPage(item.id)} aria-current={page === item.id ? "page" : undefined}><span className="nav-icon" aria-hidden="true">{item.icon}</span>{item.label}{preferences.pinnedCapabilities.includes(item.id) && item.id !== "home" && <Pin className="tiny-pin" size={11} aria-label="Pinned" />}</button>)}
        {!navigation.length && <p className="nav-empty">No capabilities shown yet. Enable one in preferences.</p>}
      </nav>
      <div className="sidebar-bottom"><button className="nav-link settings-link" type="button" onClick={() => selectPage("settings")}><Settings2 size={17} />Preferences</button><div className="profile"><span className="profile-avatar">M</span><span><strong>Morgan</strong><small>Personal workspace</small></span><span className="profile-menu">···</span></div></div>
    </aside>
    {mobileOpen && <button className="mobile-scrim" type="button" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
    <div className="main-column"><header className="topbar"><button className="mobile-menu" type="button" aria-label="Open navigation" onClick={() => setMobileOpen(true)}><Menu size={19} /></button><div className="breadcrumbs"><span>My workspace</span><span className="crumb-separator">/</span><span>{title}</span></div><div className="topbar-actions"><span className="status-indicator"><span />All clear</span><button type="button" className="theme-toggle" aria-label="Toggle light or dark theme" onClick={() => setPreferences({ ...preferences, theme: preferences.theme === "dark" ? "light" : "dark" })}>{preferences.theme === "dark" ? <Moon size={17} /> : <Sun size={17} />}</button></div></header>
      <main id="main-content" className="main-content" tabIndex={-1}>
        {page === "settings" ? <><div className="page-intro"><span className="eyebrow">PREFERENCES</span><h1>Settings</h1><p>A quieter workspace, arranged around you.</p></div><PreferenceSettings preferences={preferences} onChange={setPreferences} /></> : page === "home" ? <>
          <div className="greeting"><span className="eyebrow">WEDNESDAY, OCTOBER 8</span><h1>Good morning, Morgan<span className="greeting-period">.</span></h1><p>Here’s a little room to think about what matters.</p></div>
          <section className="home-section matters"><div className="section-title"><div><span className="eyebrow">01 / FOCUS</span><h2>What matters now?</h2></div><span className="quiet-note">A clear day starts here</span></div><EmptyState title="Nothing competing for your attention" detail="When you add projects or tasks, your next priorities will find a place here." action="Create a task" /></section>
          <div className="home-lower"><section className="home-section"><div className="section-title"><div><span className="eyebrow">02 / NEEDS YOU</span><h2>Waiting on you</h2></div></div><div className="inline-empty">No approvals or decisions are waiting.</div></section><section className="home-section"><div className="section-title"><div><span className="eyebrow">03 / IN MOTION</span><h2>Currently happening</h2></div></div><div className="inline-empty">Nothing is in progress yet.</div></section></div>
        </> : <><div className="page-intro"><span className="eyebrow">YOUR WORKSPACE</span><h1>{title}</h1><p>{capabilities.find((item) => item.id === page)?.description}.</p></div><EmptyState title={page === "tasks" ? "No tasks yet" : page === "projects" ? "No projects yet" : "No activity yet"} detail={page === "activity" ? "Changes will appear here when work is underway." : `Your ${page} will appear here when you add them.`} action={page === "tasks" ? "Create a task" : page === "projects" ? "Create a project" : undefined} />{page !== "activity" && <p className="unavailable-note">Workspace data is not connected yet. Nothing has been saved.</p>}</>}
        {page !== "settings" && <section className="ask-section" aria-label="Ask Orin"><div className="ask-heading"><span className="ask-mark"><Command size={15} /></span><span>Ask Orin</span><span className="ask-caption">A place for your next thought</span></div><form className="command-form" onSubmit={submitCommand}><label className="sr-only" htmlFor="ask-input">Ask Orin</label><input id="ask-input" value={command} onChange={(event) => { setCommand(event.target.value); setCommandMessage(""); }} placeholder="What would you like to focus on?" /><button type="submit" aria-label="Send to Orin" disabled={!command.trim()}><Send size={16} /></button><kbd>↵</kbd></form>{commandMessage && <p className="command-message" role="status">{commandMessage}</p>}</section>}
        <footer className="page-footer"><span>Thoughtfully, at your pace.</span><a href="#preferences" onClick={(event) => { event.preventDefault(); selectPage("settings"); }}>Workspace preferences <ArrowUpRight size={13} /></a></footer>
      </main>
    </div>
  </div>;
}
