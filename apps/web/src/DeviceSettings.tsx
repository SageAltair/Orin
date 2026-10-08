import { useEffect, useState, type FormEvent } from "react";
import { ApiError, request, type WorkerDevice, type WorkerJob } from "./api";

const errorText = (error: unknown) => error instanceof ApiError ? error.message : "Could not complete the request.";

export function DeviceSettings({ onApprovalCreated }: { onApprovalCreated: () => void }) {
  const [devices, setDevices] = useState<WorkerDevice[]>([]);
  const [jobs, setJobs] = useState<WorkerJob[]>([]);
  const [selected, setSelected] = useState("");
  const [name, setName] = useState("");
  const [credential, setCredential] = useState("");
  const [action, setAction] = useState("get_system_info");
  const [parameters, setParameters] = useState("{}");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    try {
      const rows = await request<WorkerDevice[]>("/devices");
      setDevices(rows);
      const target = selected || rows.find(row => row.status !== "revoked")?.id || "";
      onApprovalCreated();
      if (target) {
        setSelected(target);
        setJobs(await request<WorkerJob[]>(`/devices/${target}/jobs`));
      } else setJobs([]);
    } catch (cause) { setError(errorText(cause)); }
  };
  useEffect(() => { void refresh(); const timer = window.setInterval(() => void refresh(), 5000); return () => window.clearInterval(timer); }, [selected]);

  const register = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      const result = await request<WorkerDevice>("/devices", { method: "POST", body: JSON.stringify({ name, platform: navigator.platform || "Windows", version: "0.1.0" }) });
      setCredential(result.credential ?? ""); setName(""); setSelected(result.id); setNotice("Device registered. Copy its token now; it is shown only once."); await refresh();
    } catch (cause) { setError(errorText(cause)); } finally { setBusy(false); }
  };
  const submitJob = async (event: FormEvent) => {
    event.preventDefault(); if (!selected) return; setBusy(true); setError(""); setNotice("");
    try {
      const input = JSON.parse(parameters) as Record<string, unknown>;
      const result = await request<{ id: string }>(`/devices/${selected}/jobs`, { method: "POST", body: JSON.stringify({ action, parameters: input }) });
      setNotice(`Request sent for approval (${result.id}). The worker receives it only after approval.`); onApprovalCreated(); await refresh();
    } catch (cause) { setError(cause instanceof SyntaxError ? "Enter valid JSON parameters." : errorText(cause)); } finally { setBusy(false); }
  };

  return <section className="settings-section" aria-labelledby="devices-heading">
    <div className="section-heading"><div><span className="eyebrow">DEVICES</span><h2 id="devices-heading">Connected workers</h2></div></div>
    <p>Register each Windows worker separately. Jobs stay on hold until you approve them. Device tokens are credentials: store them securely and revoke a device if one is exposed.</p>
    {error && <p className="api-error" role="alert">{error}</p>}{notice && <p className="success-message" role="status">{notice}</p>}
    {credential && <div className="device-enrollment" role="region" aria-label="One-time device credential"><strong>Copy this one-time worker token</strong><p>It is not stored in Orin in readable form and cannot be shown again.</p><textarea aria-label="Worker token" readOnly value={credential} /><pre>{`$env:ORIN_API_URL="https://your-orin-host"
$env:ORIN_DEVICE_ID="${selected}"
$env:ORIN_WORKER_TOKEN="${credential}"
$env:ORIN_ALLOWED_ROOTS="$env:USERPROFILE\Documents"
pip install -e apps/worker
orin-worker`}</pre><button type="button" className="secondary-button" onClick={() => setCredential("")}>Hide token</button></div>}
    <form className="create-form" onSubmit={register}><label className="sr-only" htmlFor="device-name">Device name</label><input id="device-name" value={name} onChange={event => setName(event.target.value)} placeholder="Register a device (for example, Sage-PC)" maxLength={100} required /><button className="primary-button" disabled={busy || !name.trim()}>Register</button></form>
    {devices.length === 0 ? <p className="inline-empty">No worker devices registered.</p> : <div className="data-list">{devices.map(device => <article className="data-row" key={device.id}><div className="data-main"><strong>{device.name}</strong><small>{device.platform} · Worker {device.version} · <span className={`device-state state-${device.status}`}>{device.status}</span></small><small>Last seen: {device.last_seen_at ? new Date(device.last_seen_at).toLocaleString() : "Never connected"}</small></div><button type="button" className="secondary-button" disabled={device.status === "revoked"} onClick={async () => { const next = window.prompt("Rename device", device.name); if (next?.trim()) { try { await request(`/devices/${device.id}`, { method: "PATCH", body: JSON.stringify({ name: next.trim() }) }); await refresh(); } catch (cause) { setError(errorText(cause)); } } }}>Rename</button><button type="button" className="secondary-button" disabled={device.status === "revoked"} onClick={async () => { if (window.confirm(`Revoke ${device.name}? It will no longer receive jobs.`)) { try { await request(`/devices/${device.id}`, { method: "DELETE" }); await refresh(); } catch (cause) { setError(errorText(cause)); } } }}>Revoke</button></article>)}</div>}
    {devices.some(device => device.status !== "revoked") && <><form className="settings-section" onSubmit={submitJob}><h3>Request worker action</h3><p>Every worker action requires approval, including read access to your device.</p><div className="preference-controls"><label>Device<select value={selected} onChange={event => setSelected(event.target.value)}>{devices.filter(device => device.status !== "revoked").map(device => <option value={device.id} key={device.id}>{device.name} ({device.status})</option>)}</select></label><label>Capability<select value={action} onChange={event => { const next = event.target.value; setAction(next); setParameters(next === "get_system_info" ? "{}" : next === "run_allowed_command" ? '{"command":"git_status"}' : next === "write_file" ? '{"path":"C:\\\\Users\\\\you\\\\Documents\\\\file.txt","content":"text"}' : '{"path":"C:\\\\Users\\\\you\\\\Documents"}'); }}><option value="get_system_info">Read system information</option><option value="list_directory">List a directory</option><option value="read_file">Read a file</option><option value="write_file">Write a file</option><option value="run_allowed_command">Run an allowed command</option></select></label><label>Parameters (JSON)<textarea rows={4} value={parameters} onChange={event => setParameters(event.target.value)} /></label></div><button className="primary-button" disabled={busy || !selected}>Request approval</button></form><h3>Worker jobs</h3>{jobs.length ? <div className="data-list">{jobs.map(job => <article className="data-row" key={job.id}><div className="data-main"><strong>{job.action.replaceAll("_", " ")}</strong><small>{job.status}{job.progress ? ` · ${job.progress}` : ""}</small>{job.failure && <small>{job.failure}</small>}{job.result && <pre>{JSON.stringify(job.result, null, 2)}</pre>}</div></article>)}</div> : <p className="inline-empty">No worker jobs yet.</p>}</>}
  </section>;
}
