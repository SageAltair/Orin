import { useEffect, useState, type FormEvent } from "react";
import { ArrowLeft, Building2, LayoutDashboard, LogOut, Monitor, Moon, PanelLeftClose, PanelLeftOpen, ScrollText, Settings2, ShieldCheck, Sun, Users } from "lucide-react";
import { AdminConsole, type AdminSection } from "./AdminConsole";
import { ApiError, login, logout, restoreSession, type User } from "./api";

export function AdminPortal() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [dark, setDark] = useState(() => document.documentElement.dataset.theme === "dark" || window.matchMedia("(prefers-color-scheme: dark)").matches);
  const [section, setSection] = useState<AdminSection>("overview");
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("orin.admin.sidebar.collapsed") === "true");

  useEffect(() => { document.documentElement.dataset.theme = dark ? "dark" : "light"; }, [dark]);
  useEffect(() => { localStorage.setItem("orin.admin.sidebar.collapsed", String(collapsed)); }, [collapsed]);

  useEffect(() => {
    restoreSession().then(result => {
      if (result?.is_admin) setUser(result);
      else if (result) setMessage("This account does not have administrator access.");
    }).finally(() => setReady(true));
  }, []);

  const authenticate = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      const result = await login(email, password);
      if (!result.is_admin) { await logout(); setMessage("This account does not have administrator access."); return; }
      setUser(result);
    } catch (error) { setMessage(error instanceof ApiError ? error.message : "Sign-in failed."); }
    finally { setBusy(false); }
  };

  if (!ready) return <main className="admin-portal-gate"><p>Verifying administrator access…</p></main>;
  if (!user) return <main className="admin-portal-gate">
    <section className="admin-login"><ShieldCheck size={26}/><span className="eyebrow">ORIN ADMINISTRATION</span><h1>Control room</h1><p>Restricted operational access for authorized administrators.</p>
      <form onSubmit={authenticate}><label>Email<input type="email" autoComplete="username" value={email} onChange={event => setEmail(event.target.value)} required/></label><label>Password<input type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required/></label>{message && <p className="admin-login-error" role="alert">{message}</p>}<button disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button></form>
      <a href="/"><ArrowLeft size={13}/> Return to Orin</a>
    </section>
  </main>;

  const sections: { id: AdminSection; label: string; icon: typeof LayoutDashboard }[] = [
    { id: "overview", label: "Overview", icon: LayoutDashboard }, { id: "people", label: "People & access", icon: Users },
    { id: "workspaces", label: "Workspaces", icon: Building2 }, { id: "devices", label: "Worker devices", icon: Monitor },
    { id: "system", label: "System controls", icon: Settings2 }, { id: "audit", label: "Audit log", icon: ScrollText },
  ];
  return <div className={`admin-portal-shell ${collapsed ? "admin-sidebar-collapsed" : ""}`}>
    <aside className="admin-portal-rail">
      <div className="admin-rail-top"><a className="admin-portal-brand" href="/" title="Orin workspace"><span><ShieldCheck size={17}/></span><strong>orin</strong><small>ADMIN</small></a><button className="admin-collapse" type="button" onClick={() => setCollapsed(value => !value)} aria-label={collapsed ? "Expand administration sidebar" : "Collapse administration sidebar"} title={collapsed ? "Expand sidebar" : "Collapse sidebar"}>{collapsed ? <PanelLeftOpen size={16}/> : <PanelLeftClose size={16}/>}</button></div>
      <p>Administration</p>
      <nav className="admin-primary-nav" aria-label="Administration navigation">{sections.map(item => { const Icon = item.icon; return <button key={item.id} className={section === item.id ? "active" : ""} onClick={() => setSection(item.id)} aria-current={section === item.id ? "page" : undefined} title={collapsed ? item.label : undefined}><Icon size={16}/><span>{item.label}</span></button>; })}</nav>
      <div className="admin-identity"><span>Signed in as</span><strong>{user.display_name}</strong><small>{user.email}</small></div>
      <nav className="admin-utility-nav"><button onClick={() => setDark(value => !value)}>{dark ? <Sun size={15}/> : <Moon size={15}/>}<span>{dark ? "Light appearance" : "Dark appearance"}</span></button><a href="/"><ArrowLeft size={15}/><span>Open workspace</span></a><button onClick={() => logout().finally(() => setUser(null))}><LogOut size={15}/><span>Sign out</span></button></nav>
    </aside>
    <main className="admin-portal-main"><AdminConsole currentUser={user} section={section} onSectionChange={setSection}/></main>
  </div>;
}
