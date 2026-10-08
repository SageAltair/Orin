import { useEffect, useState, type FormEvent } from "react";
import { ApiError, request, type AuthSession, type User } from "./api";

const text = (error: unknown) => error instanceof ApiError ? error.message : "Could not complete the security request.";

export function AccountSecurity({ user, onUpdated }: { user: User; onUpdated: (user: User) => void }) {
  const [sessions, setSessions] = useState<AuthSession[]>([]);
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState(user.email);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const refresh = () => request<AuthSession[]>("/auth/sessions").then(setSessions).catch(cause => setError(text(cause)));
  useEffect(() => { void refresh(); }, []);
  const changeEmail = async (event: FormEvent) => {
    event.preventDefault(); setError(""); setNotice("");
    try {
      const updated = await request<User>("/auth/email", { method: "POST", body: JSON.stringify({ current_password: password, new_email: email }) });
      onUpdated(updated); setPassword(""); setNotice("Email updated. All sessions were signed out; sign in again.");
      window.setTimeout(() => window.location.reload(), 1200);
    } catch (cause) { setError(text(cause)); }
  };
  return <section className="settings-section"><div className="section-heading"><div><span className="eyebrow">SECURITY</span><h2>Email and sessions</h2></div></div>
    {error && <p className="api-error" role="alert">{error}</p>}{notice && <p role="status" className="success-message">{notice}</p>}
    <form className="preference-controls" onSubmit={changeEmail}><label>New email<input type="email" autoComplete="email" required value={email} onChange={event => setEmail(event.target.value)} /></label><label>Confirm with current password<input type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} /></label><button className="primary-button" disabled={email.toLowerCase() === user.email.toLowerCase()}>Change email</button></form>
    <h3>Sessions</h3><p>Revoke any session you do not recognize. Password and email changes revoke all sessions.</p>
    {sessions.length ? <div className="data-list">{sessions.map(item => <article className="data-row" key={item.id}><div className="data-main"><strong>{item.current ? "This session" : item.active ? "Active session" : item.revoked_at ? "Signed out" : "Expired session"}</strong><small>Created {new Date(item.created_at).toLocaleString()} · Last used {item.last_used_at ? new Date(item.last_used_at).toLocaleString() : "Not recorded"}</small></div>{item.active && <button className="secondary-button" onClick={async () => { try { await request<void>(`/auth/sessions/${item.id}`, { method: "DELETE" }); if (item.current) window.location.reload(); else await refresh(); } catch (cause) { setError(text(cause)); } }}>Revoke</button>}</article>)}</div> : <p className="inline-empty">No sessions recorded.</p>}
  </section>;
}
