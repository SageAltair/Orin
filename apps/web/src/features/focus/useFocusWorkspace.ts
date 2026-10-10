import { useCallback, useEffect, useState } from "react";
import { request } from "../../api";
import type { CloseState, DriftTrigger, Energy, FocusTask, NowState, TodayPlan } from "./types";

export function useFocusWorkspace() {
  const [now, setNow] = useState<NowState | null>(null);
  const [today, setToday] = useState<TodayPlan | null>(null);
  const [later, setLater] = useState<FocusTask[]>([]);
  const [close, setClose] = useState<CloseState | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    setError("");
    try {
      const [n, t, l, c] = await Promise.all([request<NowState>("/focus/now"), request<TodayPlan>("/focus/today"), request<FocusTask[]>("/focus/later"), request<CloseState>("/focus/close/today")]);
      setNow(n); setToday(t); setLater(l); setClose(c);
    } catch { setError("Could not load focus right now. Please try again."); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  const capture = async (title: string, details: { first_step?: string; energy_level?: Energy } = {}) => {
    setBusy(true);
    try {
      const task = await request<FocusTask>("/focus/capture", { method: "POST", body: JSON.stringify({ title, ...details }) });
      if (!today?.tasks.length) {
        try { await request("/focus/today/tasks", { method: "PUT", body: JSON.stringify({ tasks: [{ task_id: task.id, is_anchor: true }] }) }); }
        catch { setError("Saved to Inbox. You can choose the task from Today when ready."); }
      }
      void refresh(); return task;
    } catch { setError("That capture did not save. Please try again."); return null; }
    finally { setBusy(false); }
  };
  const chooseEnergy = async (energy: Energy) => {
    setBusy(true);
    try { await request("/focus/energy", { method: "PUT", body: JSON.stringify({ energy_level: energy }) }); await request("/focus/today/propose", { method: "POST" }); await refresh(); }
    catch { setError("Could not update today's plan. Please try again."); }
    finally { setBusy(false); }
  };
  const replaceToday = async (tasks: Array<{ task_id: string; is_anchor: boolean }>) => {
    try { await request("/focus/today/tasks", { method: "PUT", body: JSON.stringify({ tasks }) }); await refresh(); }
    catch { setError("Could not update today's tasks. Please try again."); }
  };
  const swap = async () => {
    const taskId = now?.task?.id; if (!taskId) return null;
    try { const result = await request<{ swapped: boolean; limit_reached: boolean; message?: string }>("/focus/today/swap", { method: "POST", body: JSON.stringify({ task_id: taskId }) }); if (result.swapped) await refresh(); return result; }
    catch { setError("Could not find another suitable task. You can rest or stay with this one."); return null; }
  };
  const start = async () => { setBusy(true); try { await request("/focus/now/start", { method: "POST", body: "{}" }); await refresh(); } catch { setError("Could not start the focus timer. Please try again."); } finally { setBusy(false); } };
  const complete = async () => { setBusy(true); try { await request("/focus/now/complete", { method: "POST", body: "{}" }); await refresh(); } catch { setError("Could not mark this task complete. Please try again."); } finally { setBusy(false); } };
  const saveFirstStep = async (task: FocusTask, first_step: string) => { try { await request(`/tasks/${task.id}`, { method: "PATCH", body: JSON.stringify({ first_step }) }); await refresh(); } catch { setError("Could not save that smaller step. Please try again."); } };
  const suggestSmallerStep = async (task: FocusTask): Promise<string | null> => {
    try {
      const result = await request<{ first_step: string }>("/focus/suggest-smaller", { method: "POST", body: JSON.stringify({ title: task.title, first_step: task.first_step, why: task.why }) });
      return result.first_step;
    } catch { return null; }
  };
  const saveClose = async (input: { drift_triggers: DriftTrigger[]; tomorrow_task_id: string | null }) => {
    setBusy(true);
    try { await request("/focus/daily-closes/today", { method: "PUT", body: JSON.stringify({ done_list: close?.done_list ?? [], drift_triggers: input.drift_triggers, tomorrow_task_id: input.tomorrow_task_id }) }); await refresh(); return true; }
    catch { setError("Could not save the close. Your notes were not recorded."); return false; }
    finally { setBusy(false); }
  };
  return { now, today, later, close, error, busy, refresh, capture, chooseEnergy, replaceToday, swap, start, complete, saveFirstStep, suggestSmallerStep, saveClose };
}
