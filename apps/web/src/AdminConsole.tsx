import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Check, RefreshCw, Search, Shield, Users } from "lucide-react";
import { ApiError, request, type User } from "./api";

type Overview = {
  generated_at: string;
  totals: { users: number; active_users: number; workspaces: number; projects: number; tasks: number; attachments: number; storage_bytes: number };
  operations: { active_sessions: number; pending_approvals: number; commands_30d: number; active_workers: number };
  ai: { requests_30d: number; failures_30d: number; fallbacks_30d: number; estimated_cost_microusd_30d: number; success_rate: number };
};
type AdminUser = User & { workspace_count: number; project_count: number; task_count: number; active_sessions: number };
type WorkspaceRow = { id: string; name: string; owner_email: string; project_count: number; task_count: number; updated_at: string };
type DeviceRow = { id: string; name: string; owner_email: string; platform: string; version: string; status: string; last_seen_at: string | null };
type AdminSettings = { registration_enabled: boolean };
type AuditRow = { id: string; action: string; target_type: string; target_id: string | null; detail: Record<string, unknown>; actor_email: string; created_at: string };
export type AdminSection = "overview" | "people" | "workspaces" | "devices" | "system" | "audit";

const formatStorage = (bytes: number) => bytes < 1024 * 1024 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
const formatCost = (microUsd: number) => new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(microUsd / 1_000_000);

export function AdminConsole({ currentUser, section, onSectionChange }: { currentUser: User; section: AdminSection; onSectionChange: (section: AdminSection) => void }) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceRow[]>([]);
  const [devices, setDevices] = useState<DeviceRow[]>([]);
  const [settings, setSettings] = useState<AdminSettings>({ registration_enabled: true });
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setBusy(true); setMessage("");
    try {
      const [summary, people, spaces, deviceRows, systemSettings, auditRows] = await Promise.all([
        request<Overview>("/admin/overview"),
        request<{ items: AdminUser[] }>(`/admin/users?query=${encodeURIComponent(query)}`),
        request<WorkspaceRow[]>("/admin/workspaces"),
        request<DeviceRow[]>("/admin/devices"),
        request<AdminSettings>("/admin/settings"),
        request<AuditRow[]>("/admin/audit"),
      ]);
      setOverview(summary); setUsers(people.items); setWorkspaces(spaces); setDevices(deviceRows); setSettings(systemSettings); setAudit(auditRows);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "Administration data could not be loaded.");
    } finally { setBusy(false); }
  }, [query]);

  useEffect(() => { void load(); }, [load]);

  const updateUser = async (user: AdminUser, disabled: boolean) => {
    setBusy(true); setMessage("");
    try {
      await request(`/admin/users/${user.id}`, { method: "PATCH", body: JSON.stringify({ is_disabled: disabled }) });
      setUsers(rows => rows.map(row => row.id === user.id ? { ...row, is_disabled: disabled, active_sessions: disabled ? 0 : row.active_sessions } : row));
      setMessage(disabled ? `${user.display_name} has been disabled.` : `${user.display_name} has been restored.`);
    } catch (error) { setMessage(error instanceof ApiError ? error.message : "Account could not be updated."); }
    finally { setBusy(false); }
  };

  const revokeSessions = async (user: AdminUser) => {
    setBusy(true); setMessage("");
    try {
      await request(`/admin/users/${user.id}/revoke-sessions`, { method: "POST" });
      setUsers(rows => rows.map(row => row.id === user.id ? { ...row, active_sessions: 0 } : row));
      setMessage(`Sessions for ${user.display_name} have been revoked.`);
    } catch (error) { setMessage(error instanceof ApiError ? error.message : "Sessions could not be revoked."); }
    finally { setBusy(false); }
  };

  const updateRole = async (user: AdminUser, isAdmin: boolean) => {
    setBusy(true); setMessage("");
    try {
      await request(`/admin/users/${user.id}`, { method: "PATCH", body: JSON.stringify({ is_admin: isAdmin }) });
      setUsers(rows => rows.map(row => row.id === user.id ? { ...row, is_admin: isAdmin } : row));
      setMessage(`${user.display_name} is ${isAdmin ? "now an administrator" : "now a standard user"}.`);
    } catch (error) { setMessage(error instanceof ApiError ? error.message : "Role could not be updated."); }
    finally { setBusy(false); }
  };

  const removeWorkspace = async (space: WorkspaceRow) => {
    setBusy(true); setMessage("");
    try { await request(`/admin/workspaces/${space.id}`, { method: "DELETE" }); setWorkspaces(rows => rows.filter(row => row.id !== space.id)); setMessage(`${space.name} was deleted.`); }
    catch (error) { setMessage(error instanceof ApiError ? error.message : "Workspace could not be deleted."); }
    finally { setBusy(false); }
  };

  const revokeDevice = async (device: DeviceRow) => {
    setBusy(true); setMessage("");
    try { await request(`/admin/devices/${device.id}/revoke`, { method: "POST" }); setDevices(rows => rows.map(row => row.id === device.id ? { ...row, status: "revoked" } : row)); setMessage(`${device.name} was revoked.`); }
    catch (error) { setMessage(error instanceof ApiError ? error.message : "Device could not be revoked."); }
    finally { setBusy(false); }
  };

  const setRegistration = async (enabled: boolean) => {
    setBusy(true); setMessage("");
    try { const result = await request<AdminSettings>("/admin/settings", { method: "PUT", body: JSON.stringify({ registration_enabled: enabled }) }); setSettings(result); setMessage(`Public registration is ${enabled ? "open" : "closed"}.`); }
    catch (error) { setMessage(error instanceof ApiError ? error.message : "System setting could not be saved."); }
    finally { setBusy(false); }
  };

  const cleanup = async () => {
    setBusy(true); setMessage("");
    try { const result = await request<Record<string, number>>("/admin/maintenance/cleanup", { method: "POST" }); setMessage(`Cleanup completed: ${Object.values(result).reduce((a, b) => a + b, 0)} expired records removed.`); }
    catch (error) { setMessage(error instanceof ApiError ? error.message : "Cleanup could not be completed."); }
    finally { setBusy(false); }
  };

  if (!overview) return <div className="admin-loading" role="status">{message || "Loading administration…"}</div>;
  const selectedUser = users.find(user => user.id === selected);
  return <section className="admin-console" aria-labelledby="admin-title">
    <header className="admin-header">
      <div><span className="eyebrow"><Shield size={13}/> SYSTEM ADMINISTRATION</span><h1 id="admin-title">Control room</h1><p>System health, access, usage and operational oversight.</p></div>
      <button className="admin-refresh" type="button" onClick={() => void load()} disabled={busy} aria-label="Refresh administration data"><RefreshCw size={15}/><span>Refresh</span></button>
    </header>
    {message && <p className="admin-message" role="status">{message}</p>}
    {section === "overview" && <>
      <div className="admin-metrics" aria-label="System totals">
        <div><strong>{overview.totals.active_users}</strong><span>Active people</span><small>{overview.totals.users} registered</small></div>
        <div><strong>{overview.totals.workspaces}</strong><span>Workspaces</span><small>{overview.totals.projects} projects</small></div>
        <div><strong>{overview.operations.commands_30d}</strong><span>AI commands</span><small>Last 30 days</small></div>
        <div><strong>{overview.ai.success_rate}%</strong><span>AI success</span><small>{overview.ai.fallbacks_30d} fallbacks</small></div>
      </div>
      <div className="admin-overview-grid">
        <section className="admin-panel"><header><h2>Operations</h2><span className="admin-health"><Check size={13}/> Operational</span></header>
          <dl className="admin-definition-list">
            <div><dt>Active sessions</dt><dd>{overview.operations.active_sessions}</dd></div>
            <div><dt>Pending approvals</dt><dd className={overview.operations.pending_approvals ? "attention" : ""}>{overview.operations.pending_approvals}</dd></div>
            <div><dt>Connected workers</dt><dd>{overview.operations.active_workers}</dd></div>
            <div><dt>Managed tasks</dt><dd>{overview.totals.tasks}</dd></div>
            <div><dt>File storage</dt><dd>{formatStorage(overview.totals.storage_bytes)}</dd></div>
          </dl>
        </section>
        <section className="admin-panel"><header><h2>AI routing · 30 days</h2><small>{formatCost(overview.ai.estimated_cost_microusd_30d)} estimated</small></header>
          <div className="admin-reliability"><strong>{overview.ai.requests_30d}</strong><span>requests</span><div><i style={{ width: `${overview.ai.success_rate}%` }}/></div></div>
          <dl className="admin-definition-list compact"><div><dt>Successful</dt><dd>{overview.ai.requests_30d - overview.ai.failures_30d}</dd></div><div><dt>Failed</dt><dd>{overview.ai.failures_30d}</dd></div><div><dt>Automatic fallbacks</dt><dd>{overview.ai.fallbacks_30d}</dd></div></dl>
        </section>
      </div>
      <section className="admin-action-center"><header><div><span className="eyebrow">ACTION CENTER</span><h2>Needs attention</h2></div><small>Live operational exceptions</small></header><div>
        <button onClick={() => onSectionChange("people")}><span>Disabled accounts</span><strong>{overview.totals.users - overview.totals.active_users}</strong><small>Review access</small></button>
        <button onClick={() => onSectionChange("devices")}><span>Worker devices</span><strong>{devices.filter(device => device.status !== "revoked").length}</strong><small>Inspect connections</small></button>
        <button onClick={() => onSectionChange("system")}><span>Pending approvals</span><strong>{overview.operations.pending_approvals}</strong><small>Check policy state</small></button>
        <button onClick={() => onSectionChange("audit")}><span>Admin changes</span><strong>{audit.length}</strong><small>Review audit log</small></button>
      </div></section>
    </>}

    {section === "people" && <section className="admin-panel admin-table-panel">
      <header><div><h2>People and access</h2><small>{users.length} accounts shown</small></div><label className="admin-search"><Search size={14}/><span className="sr-only">Search people</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search name or email"/></label></header>
      <div className="admin-table" role="table" aria-label="User accounts">
        <div className="admin-table-head" role="row"><span>Account</span><span>Work</span><span>Sessions</span><span>Status</span></div>
        {users.map(user => <div key={user.id} className={`admin-user-row ${selected === user.id ? "selected" : ""}`} role="row" onClick={() => setSelected(user.id)}>
          <span><b>{user.display_name}</b><small>{user.email}</small></span><span>{user.project_count} projects · {user.task_count} tasks</span><span>{user.active_sessions}</span><span className={user.is_disabled ? "status-disabled" : "status-active"}>{user.is_admin ? "Administrator" : user.is_disabled ? "Disabled" : "Active"}</span>
        </div>)}
      </div>
      {selectedUser && <aside className="admin-selection"><div><Users size={16}/><span><strong>{selectedUser.display_name}</strong><small>{selectedUser.workspace_count} workspaces · joined {new Date(selectedUser.created_at).toLocaleDateString()}</small></span></div><div>{selectedUser.id !== currentUser.id && <button type="button" onClick={() => void updateRole(selectedUser, !selectedUser.is_admin)} disabled={busy}>{selectedUser.is_admin ? "Remove admin" : "Make admin"}</button>}{selectedUser.id !== currentUser.id && !selectedUser.is_admin && <button type="button" onClick={() => void updateUser(selectedUser, !selectedUser.is_disabled)} disabled={busy}>{selectedUser.is_disabled ? "Restore account" : "Disable account"}</button>}{selectedUser.id !== currentUser.id && <button type="button" onClick={() => void revokeSessions(selectedUser)} disabled={busy || selectedUser.active_sessions === 0}>Revoke sessions</button>}</div></aside>}
    </section>}

    {section === "workspaces" && <section className="admin-panel admin-table-panel"><header><div><h2>Workspace management</h2><small>Empty workspaces can be removed safely</small></div></header><div className="admin-table workspace-table" role="table" aria-label="Workspaces"><div className="admin-table-head" role="row"><span>Workspace</span><span>Owner</span><span>Projects</span><span>Control</span></div>{workspaces.map(space => <div className="admin-user-row" role="row" key={space.id}><span><b>{space.name}</b><small>{space.task_count} tasks · updated {new Date(space.updated_at).toLocaleDateString()}</small></span><span>{space.owner_email}</span><span>{space.project_count}</span><span>{space.project_count === 0 && space.task_count === 0 ? <button className="admin-row-action" onClick={() => void removeWorkspace(space)} disabled={busy}>Delete</button> : "In use"}</span></div>)}</div></section>}
    {section === "devices" && <section className="admin-panel admin-table-panel"><header><div><h2>Worker devices</h2><small>Revoke unrecognized or compromised workers</small></div></header><div className="admin-table workspace-table"><div className="admin-table-head"><span>Device</span><span>Owner</span><span>Status</span><span>Control</span></div>{devices.map(device => <div className="admin-user-row" key={device.id}><span><b>{device.name}</b><small>{device.platform} · {device.version}</small></span><span>{device.owner_email}</span><span>{device.status}</span><span>{device.status !== "revoked" ? <button className="admin-row-action" onClick={() => void revokeDevice(device)} disabled={busy}>Revoke</button> : "Revoked"}</span></div>)}</div></section>}
    {section === "system" && <section className="admin-system-controls"><div><h2>Access policy</h2><p>Control whether new people can create accounts.</p><label className="admin-switch"><input type="checkbox" checked={settings.registration_enabled} onChange={event => void setRegistration(event.target.checked)} disabled={busy}/><span>Public registration</span><small>{settings.registration_enabled ? "Open" : "Closed"}</small></label></div><div><h2>Data maintenance</h2><p>Remove expired sessions, refresh tokens and stale rate-limit windows.</p><button className="admin-maintenance-action" type="button" onClick={() => void cleanup()} disabled={busy}>Run cleanup</button></div></section>}
    {section === "audit" && <section className="admin-panel admin-audit-panel"><header><div><h2>Administrator audit log</h2><small>Immutable record of privileged changes</small></div></header><ol>{audit.map(event => <li key={event.id}><time>{new Date(event.created_at).toLocaleString()}</time><div><strong>{event.action.replaceAll(".", " ")}</strong><span>{event.actor_email}</span></div><code>{event.target_type}{event.target_id ? ` · ${event.target_id}` : ""}</code></li>)}{audit.length === 0 && <li className="admin-empty-state">No administrator changes have been recorded.</li>}</ol></section>}
    {overview.operations.pending_approvals > 0 && section === "overview" && <p className="admin-advisory"><AlertTriangle size={15}/> {overview.operations.pending_approvals} approval request{overview.operations.pending_approvals === 1 ? " is" : "s are"} waiting for review.</p>}
  </section>;
}
