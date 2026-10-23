import { useState, type KeyboardEvent, type ReactNode } from "react";
import { Check } from "lucide-react";
import type { Theme, UserPreferences } from "../capabilities";

export const settingsSections = [
  ["appearance", "Appearance"],
  ["workspace", "Workspace"],
  ["account", "Account"],
  ["intelligence", "Intelligence"],
  ["approvals", "Approvals"],
  ["notifications", "Notifications"],
  ["devices", "Devices"],
  ["integrations", "Integrations"],
  ["privacy", "Your data"],
] as const;
export type SettingsSection = (typeof settingsSections)[number][0];

/** Panels stay mounted, so changing sections cannot discard an unfinished form. */
export function SettingsWorkspace({ children }: { children: (section: SettingsSection) => ReactNode }) {
  const [section, setSection] = useState<SettingsSection>("appearance");
  const navigate = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step = event.key === "ArrowDown" || event.key === "ArrowRight" ? 1
      : event.key === "ArrowUp" || event.key === "ArrowLeft" ? -1 : 0;
    const next = event.key === "Home" ? 0 : event.key === "End" ? settingsSections.length - 1
      : step ? (index + step + settingsSections.length) % settingsSections.length : -1;
    if (next < 0) return;
    event.preventDefault();
    const id = settingsSections[next][0];
    setSection(id);
    document.getElementById(`settings-nav-${id}`)?.focus();
  };
  return (
    <div className="workspace-settings-layout">
      <nav className="workspace-settings-nav" aria-label="Settings sections">
        {settingsSections.map(([id, label], index) => (
          <button key={id} id={`settings-nav-${id}`} type="button"
            aria-current={id === section ? "page" : undefined}
            aria-controls="settings-panel" onClick={() => setSection(id)}
            onKeyDown={event => navigate(event, index)}>{label}</button>
        ))}
      </nav>
      <div id="settings-panel" className="workspace-settings-panel" aria-labelledby={`settings-nav-${section}`}>
        {children(section)}
      </div>
    </div>
  );
}

const themes: { id: Theme; title: string; detail: string }[] = [
  { id: "light", title: "Light", detail: "A warm, clear canvas" },
  { id: "dark", title: "Dark", detail: "A softer light for late work" },
  { id: "system", title: "System", detail: "Follow your device" },
];
export function AppearanceSettings({ preferences, onChange }: {
  preferences: UserPreferences;
  onChange: (preferences: UserPreferences) => void;
}) {
  return <section className="appearance-settings settings-section" aria-labelledby="appearance-heading">
    <h2 id="appearance-heading">A familiar kind of calm.</h2>
    <p>Choose the light that suits your work.</p>
    <div className="appearance-themes" role="group" aria-label="Colour theme">
      {themes.map(theme => <button type="button" key={theme.id}
        className={`appearance-theme ${theme.id}`} aria-pressed={preferences.theme === theme.id}
        onClick={() => onChange({ ...preferences, theme: theme.id })}>
        <span className="appearance-swatch" aria-hidden="true"><i /><span><b /><b /><b /></span></span>
        <span className="appearance-theme-label">{theme.title}{preferences.theme === theme.id && <Check size={14} />}</span>
        <small>{theme.detail}</small>
      </button>)}
    </div>
    <div className="workspace-preference-row">
      <div><h3>Interface density</h3><p>A little more breathing room, or a more compact view.</p></div>
      <select aria-label="Interface density" value={preferences.density}
        onChange={event => onChange({ ...preferences, density: event.target.value as UserPreferences["density"] })}>
        <option value="comfortable">Comfortable</option><option value="compact">Compact</option>
      </select>
    </div>
    <p className="appearance-note">The same workspace, in every light. Changes follow you across Orin.</p>
  </section>;
}
