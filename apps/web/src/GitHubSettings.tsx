import { useCallback, useEffect, useState } from "react";
import { ApiError, Project, request } from "./api";

type GitHubStatus = { connected: boolean; account_login: string | null; granted_scopes: string[]; capabilities: string[]; last_successful_sync_at: string | null };
type Repository = { id: string; full_name: string; private: boolean; html_url: string | null; default_branch: string | null; selected_project_ids: string[] };
type RepositoryContext = { repository: string; issues: Array<{ number: number; title: string; state: string; url: string | null }>; pull_requests: Array<{ number: number; title: string; state: string; url: string | null; draft: boolean }>; last_successful_sync_at: string };
const errorText = (cause: unknown) => cause instanceof ApiError ? cause.message : "GitHub could not be reached. Retry the operation.";

export function GitHubSettings({ projects }: { projects: Project[] }) {
  const [status, setStatus] = useState<GitHubStatus | null>(null);
  const [repos, setRepos] = useState<Repository[]>([]);
  const [projectId, setProjectId] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [context, setContext] = useState<RepositoryContext | null>(null);
  const refresh = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const next = await request<GitHubStatus>("/integrations/github");
      setStatus(next);
      setRepos(next.connected ? await request<Repository[]>("/integrations/github/repositories") : []);
    } catch (cause) { setError(errorText(cause)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  const connect = async () => {
    setBusy(true); setError("");
    try {
      const result = await request<{ authorization_url: string }>("/integrations/github/connect", { method: "POST" });
      window.location.assign(result.authorization_url);
    } catch (cause) { setError(errorText(cause)); setBusy(false); }
  };
  const disconnect = async () => {
    setBusy(true); setError(""); setMessage("");
    try { await request<void>("/integrations/github", { method: "DELETE" }); setStatus(current => current ? { ...current, connected: false, account_login: null } : current); setRepos([]); setMessage("GitHub disconnected and its saved credential was removed."); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  };
  const selectRepository = async (repository: Repository) => {
    if (!projectId) { setError("Choose a project first."); return; }
    setBusy(true); setError(""); setMessage("");
    try {
      await request(`/integrations/github/projects/${projectId}/repository`, { method: "PUT", body: JSON.stringify({ provider_resource_id: repository.id }) });
      setRepos(current => current.map(item => item.id === repository.id
        ? { ...item, selected_project_ids: [...new Set([...item.selected_project_ids, projectId])] } : item));
      setMessage(`${repository.full_name} is now a project source.`);
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  };
  const loadContext = async () => {
    if (!projectId) { setError("Choose a project first."); return; }
    setBusy(true); setError(""); setContext(null);
    try { setContext(await request<RepositoryContext>(`/integrations/github/projects/${projectId}/issues`)); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  };

  return <section className="settings-section github-settings" aria-labelledby="github-heading">
    <div className="section-heading"><div><span className="eyebrow">INTEGRATIONS</span><h2 id="github-heading">GitHub</h2></div></div>
    <p>Connect a GitHub App to read installed repositories, issues, and pull requests. Orin does not write to repositories.</p>
    {error && <div className="api-error" role="alert">{error} <button className="secondary-button" onClick={() => void refresh()}>Retry</button></div>}
    {message && <p className="success-message" role="status">{message}</p>}
    {loading ? <p role="status">Loading GitHub connection…</p> : status?.connected ? <>
      <p>Connected as <strong>{status.account_login}</strong>{status.last_successful_sync_at ? ` · Last sync ${new Date(status.last_successful_sync_at).toLocaleString()}` : ""}</p>
      <div className="github-actions"><button className="secondary-button" disabled={busy} onClick={() => void refresh()}>Refresh repositories</button><button className="secondary-button" disabled={busy} onClick={() => void disconnect()}>Disconnect GitHub</button></div>
      <label className="project-picker">Select a project for repository context<select value={projectId} onChange={event => setProjectId(event.target.value)}><option value="">Choose a project</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
      {repos.length ? <div className="data-list">{repos.map(repo => { const selectedHere = Boolean(projectId && repo.selected_project_ids.includes(projectId)); return <article className="data-row" key={repo.id}><div className="data-main"><strong>{repo.html_url ? <a href={repo.html_url} target="_blank" rel="noreferrer">{repo.full_name}</a> : repo.full_name}</strong><small>{repo.private ? "Private" : "Public"}{repo.default_branch ? ` · ${repo.default_branch}` : ""}{selectedHere ? " · Selected for this project" : ""}</small></div><div className="github-repo-actions"><button className="secondary-button" disabled={busy || !projectId} onClick={() => void selectRepository(repo)}>{selectedHere ? "Selected" : "Select"}</button>{selectedHere && <button className="secondary-button" disabled={busy} onClick={() => void loadContext()}>View issues and PRs</button>}</div></article>; })}</div> : <p className="inline-empty">No repositories are available to this GitHub App installation.</p>}
      {context && <section className="github-context" aria-label={`${context.repository} issues and pull requests`}><h3>{context.repository}</h3><p>Synced {new Date(context.last_successful_sync_at).toLocaleString()}</p><h4>Issues</h4>{context.issues.length ? <ul>{context.issues.map(issue => <li key={issue.number}>{issue.url ? <a href={issue.url} target="_blank" rel="noreferrer">#{issue.number} {issue.title}</a> : `#${issue.number} ${issue.title}`} · {issue.state}</li>)}</ul> : <p>No issues returned.</p>}<h4>Pull requests</h4>{context.pull_requests.length ? <ul>{context.pull_requests.map(pull => <li key={pull.number}>{pull.url ? <a href={pull.url} target="_blank" rel="noreferrer">#{pull.number} {pull.title}</a> : `#${pull.number} ${pull.title}`} · {pull.state}{pull.draft ? " · draft" : ""}</li>)}</ul> : <p>No pull requests returned.</p>}</section>}
    </> : <><p>Not connected.</p><button className="primary-button" disabled={busy} onClick={() => void connect()}>Connect GitHub</button></>}
  </section>;
}
