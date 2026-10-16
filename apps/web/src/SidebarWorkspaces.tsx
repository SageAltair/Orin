import { useEffect, useState, type CSSProperties, type FormEvent } from "react";
import { Check, Plus, X } from "lucide-react";

export type SidebarWorkspace = { id: string; name: string; color: string };

const palette = ["#6b73ff", "#8a63d2", "#2da6b5", "#26a269", "#dd7a32"];

export function workspaceStorageKey(userId: string) {
  return `orin.sidebar-workspaces.${userId}.v1`;
}

export function readWorkspaces(userId: string): SidebarWorkspace[] {
  const fallback = [{ id: "personal", name: "Personal", color: palette[0] }];
  try {
    const parsed = JSON.parse(localStorage.getItem(workspaceStorageKey(userId)) || "null") as SidebarWorkspace[] | null;
    return parsed?.length ? parsed : fallback;
  } catch {
    return fallback;
  }
}

export function SidebarWorkspaces({ userId, onActiveChange }: { userId: string; onActiveChange: (name: string) => void }) {
  const [items, setItems] = useState<SidebarWorkspace[]>(() => readWorkspaces(userId));
  const [activeId, setActiveId] = useState(() => localStorage.getItem(`${workspaceStorageKey(userId)}.active`) || "personal");
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [color, setColor] = useState(palette[1]);

  useEffect(() => {
    const active = items.find(item => item.id === activeId) || items[0];
    if (active) onActiveChange(active.name);
  }, [activeId, items, onActiveChange]);

  const select = (item: SidebarWorkspace) => {
    setActiveId(item.id);
    localStorage.setItem(`${workspaceStorageKey(userId)}.active`, item.id);
  };
  const create = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    const item = { id: crypto.randomUUID(), name: trimmed.slice(0, 48), color };
    const next = [...items, item];
    setItems(next);
    localStorage.setItem(workspaceStorageKey(userId), JSON.stringify(next));
    select(item);
    setName("");
    setCreating(false);
  };

  return <section className="sidebar-workspaces" aria-label="Workspaces">
    <span className="nav-label">WORKSPACES</span>
    <div className="workspace-list">
      {items.map(item => <button type="button" className={`workspace-item ${activeId === item.id ? "active" : ""}`} key={item.id} onClick={() => select(item)}>
        <span className="workspace-item-icon" style={{ "--workspace-color": item.color } as CSSProperties}>{item.name.slice(0, 1).toUpperCase()}</span>
        <span>{item.name}</span>
        <span className="workspace-status" style={{ background: item.color }} />
        {activeId === item.id && <Check className="workspace-check" size={12} />}
      </button>)}
    </div>
    <button type="button" className="new-workspace-button" onClick={() => setCreating(true)}><Plus size={15} />New workspace</button>
    {creating && <div className="workspace-dialog-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) setCreating(false); }}>
      <form className="workspace-dialog" role="dialog" aria-modal="true" aria-labelledby="new-workspace-title" onSubmit={create}>
        <header><div><span className="eyebrow">WORKSPACES</span><h2 id="new-workspace-title">Create a workspace</h2></div><button type="button" aria-label="Close workspace dialog" onClick={() => setCreating(false)}><X size={18} /></button></header>
        <p>Give this area a clear name so related projects and work are easy to find.</p>
        <label>Workspace name<input autoFocus required maxLength={48} value={name} onChange={event => setName(event.target.value)} placeholder="e.g. Content & Media" /></label>
        <fieldset><legend>Color</legend><div className="workspace-colors">{palette.map(value => <button type="button" key={value} aria-label={`Choose ${value}`} aria-pressed={color === value} style={{ background: value }} onClick={() => setColor(value)}>{color === value && <Check size={14} />}</button>)}</div></fieldset>
        <footer><button type="button" className="secondary-button" onClick={() => setCreating(false)}>Cancel</button><button className="primary-button" disabled={!name.trim()}>Create workspace</button></footer>
      </form>
    </div>}
  </section>;
}
