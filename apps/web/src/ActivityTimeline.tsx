import { useCallback, useEffect, useState } from "react";
import { Activity, ApiError, request } from "./api";

const pageSize = 30;
const eventTypes = ["command_received", "intent_interpreted", "plan_created", "command_completed", "command_failed", "policy_decision", "approval_requested", "approval_decided", "worker_connected", "worker_disconnected", "worker_job_queued", "worker_job_started", "worker_job_progress", "worker_job_completed", "worker_job_failed", "worker_job_cancelled", "worker_job_timed_out", "integration_operation", "project_created", "project_updated", "task_created", "task_updated", "memory_changed", "focus_updated"];

type ActivityTimelineProps = { onOpenProject: (projectId: string) => void; onOpenTask: (taskId: string) => void };

export function ActivityTimeline({ onOpenProject, onOpenTask }: ActivityTimelineProps) {
  const [rows, setRows] = useState<Activity[]>([]);
  const [eventType, setEventType] = useState("");
  const [relatedFilter, setRelatedFilter] = useState<{ kind: "command" | "execution"; id: string } | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState("");
  const fetchPage = useCallback(async (start: number, replace: boolean) => {
    setLoading(true); setError("");
    try {
      const query = new URLSearchParams({ limit: String(pageSize), offset: String(start) });
      if (eventType) query.set("event_type", eventType);
      if (relatedFilter) query.set(`${relatedFilter.kind}_id`, relatedFilter.id);
      const result = await request<Activity[]>(`/activity?${query.toString()}`);
      setRows(current => replace ? result : [...current, ...result]);
      setOffset(start + result.length); setHasMore(result.length === pageSize);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Activity could not be loaded.");
    } finally { setLoading(false); }
  }, [eventType, relatedFilter]);
  useEffect(() => { setRows([]); setOffset(0); setHasMore(true); void fetchPage(0, true); }, [fetchPage]);

  return <section className="activity-page" aria-label="Activity timeline">
    <div className="activity-toolbar"><label>Event type<select value={eventType} onChange={event => setEventType(event.target.value)}><option value="">All activity</option>{eventTypes.map(type => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}</select></label>{relatedFilter ? <button className="secondary-button" onClick={() => setRelatedFilter(null)}>Clear {relatedFilter.kind} filter</button> : <span>{rows.length} events loaded</span>}</div>
    {error && <div className="activity-error" role="alert"><p>{error}</p><button className="secondary-button" onClick={() => void fetchPage(offset, rows.length === 0)}>Retry</button></div>}
    {!loading && !error && rows.length === 0 && <div className="empty-state"><span className="empty-mark" aria-hidden="true">○</span><h3>No activity yet</h3><p>Commands and changes to your work will appear here.</p></div>}
    {rows.length > 0 && <ol className="activity-list">{rows.map(item => <li className="activity-item" key={item.id}>
      <span className={`activity-dot severity-${item.severity ?? "info"}`} aria-hidden="true" />
      <div className="activity-main"><div className="activity-title"><strong>{item.summary}</strong><span className={`activity-status status-${(item.result_status ?? "succeeded").replaceAll("_", "-")}`}>{(item.result_status ?? "succeeded").replaceAll("_", " ")}</span></div>
        <small>{item.activity_type.replaceAll("_", " ")} · {new Date(item.created_at).toLocaleString()}</small>
        <div className="activity-links">{item.project_id && <button type="button" onClick={() => onOpenProject(item.project_id!)}>Project {item.project_id.slice(0, 8)}</button>}{item.task_id && <button type="button" onClick={() => onOpenTask(item.task_id!)}>Task {item.task_id.slice(0, 8)}</button>}{item.command_id && <button type="button" onClick={() => setRelatedFilter({ kind: "command", id: item.command_id! })}>Command {item.command_id.slice(0, 8)}</button>}{item.execution_id && <button type="button" onClick={() => setRelatedFilter({ kind: "execution", id: item.execution_id! })}>Execution {item.execution_id.slice(0, 8)}</button>}{item.approval_id && <span>Approval {item.approval_id.slice(0, 8)}</span>}{item.worker_job_id && <span>Worker job {item.worker_job_id.slice(0, 8)}</span>}</div>
      </div>
    </li>)}</ol>}
    {loading && <p className="activity-loading" role="status">Loading activity…</p>}
    {!loading && hasMore && rows.length > 0 && <button className="secondary-button activity-more" onClick={() => void fetchPage(offset, false)}>Load more</button>}
  </section>;
}
