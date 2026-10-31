import { useEffect, useState, type CSSProperties, type FormEvent } from "react";
import { Check, Plus, X } from "lucide-react";
import { request, setActiveWorkspace } from "./api";

export type SidebarWorkspace = { id: string; name: string; color: string };

const palette = ["#6b73ff", "#8a63d2", "#2da6b5", "#26a269", "#dd7a32"];

export function workspaceStorageKey(userId: string) {
  return `orin.sidebar-workspaces.${userId}.v1`;
}

export function SidebarWorkspaces({ userId, onActiveChange }: { userId: string; onActiveChange: (workspace: SidebarWorkspace) => boolean | Promise<boolean> }) {
  const [items, setItems] = useState<SidebarWorkspace[]>([]);
  const [activeId, setActiveId] = useState(() => localStorage.getItem(`${workspaceStorageKey(userId)}.active`) || "");
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [color, setColor] = useState(palette[1]);
  const [error, setError] = useState("");

  useEffect(() => {
    void request<SidebarWorkspace[]>("/workspaces").then(response => {
      const rows = Array.isArray(response) && response.length ? response : [{ id: "", name: "Personal", color: palette[0] }];
      setItems(rows);
      const selected = rows.find(item => item.id === activeId) || rows[0];
      if (selected) void select(selected);
    }).catch(() => {
      const fallback = { id: "", name: "Personal", color: palette[0] };
      setItems([fallback]);
      void select(fallback);
    });
  }, [userId]);

  const select = async (item: SidebarWorkspace) => {
    try {
      // Parent must revoke the old browser lease before any visible/API
      // workspace selection changes. Never optimistically switch first.
      const allowed = await onActiveChange(item);
      if (!allowed) {
        setError("Workspace switch blocked until reminder authorization is revoked.");
        return;
      }
      setError("");
      setActiveId(item.id);
      setActiveWorkspace(item.id);
      localStorage.setItem(`${workspaceStorageKey(userId)}.active`, item.id);
    } catch {
      setError("Workspace switch failed. Retry when Orin is reachable.");
    }
  };
  const create = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setError("");
    try {
      const item = await request<SidebarWorkspace>("/workspaces", { method: "POST", body: JSON.stringify({ name: trimmed.slice(0, 48), color }) });
      setItems(current => [...current, item]);
      void select(item);
      setName("");
      setCreating(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create this workspace.");
    }
  };

  return <section className="sidebar-workspaces" aria-label="Workspaces">
    <span className="nav-label">WORKSPACES</span>
    {error && <p role="alert">{error}</p>}
    <div className="workspace-list">
      {items.map(item => <button type="button" className={`workspace-item ${activeId === item.id ? "active" : ""}`} key={item.id} onClick={() => void select(item)} aria-label={item.name} title={item.name}>
        <span className="workspace-item-icon" style={{ "--workspace-color": item.color } as CSSProperties}>{item.name.slice(0, 1).toUpperCase()}</span>
        <span className="workspace-item-label">{item.name}</span>
        <span className="workspace-status" style={{ background: item.color }} />
        {activeId === item.id && <Check className="workspace-check" size={12} />}
      </button>)}
    </div>
    <button type="button" className="new-workspace-button" aria-label="New workspace" title="New workspace" onClick={() => setCreating(true)}><Plus size={15} /><span>New workspace</span></button>
    {creating && <div className="workspace-dialog-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) setCreating(false); }}>
      <form className="workspace-dialog" role="dialog" aria-modal="true" aria-labelledby="new-workspace-title" onSubmit={create}>
        <header><div><span className="eyebrow">WORKSPACES</span><h2 id="new-workspace-title">Create a workspace</h2></div><button type="button" aria-label="Close workspace dialog" onClick={() => setCreating(false)}><X size={18} /></button></header>
        <p>Give this area a clear name so related projects and work are easy to find.</p>
        {error && <p className="api-error" role="alert">{error}</p>}
        <label>Workspace name<input autoFocus required maxLength={48} value={name} onChange={event => setName(event.target.value)} placeholder="e.g. Content & Media" /></label>
        <fieldset><legend>Color</legend><div className="workspace-colors">{palette.map(value => <button type="button" key={value} aria-label={`Choose ${value}`} aria-pressed={color === value} style={{ background: value }} onClick={() => setColor(value)}>{color === value && <Check size={14} />}</button>)}</div></fieldset>
        <footer><button type="button" className="secondary-button" onClick={() => setCreating(false)}>Cancel</button><button className="primary-button" disabled={!name.trim()}>Create workspace</button></footer>
      </form>
    </div>}
  </section>;
}
