import type { Task } from "../../api";

export type Energy = "low" | "medium" | "high";
export type DriftTrigger = "app" | "thought" | "emotion" | "person" | "tired" | "other";
export interface CaptureSuggestion { title: string; first_step: string; energy_level: Energy }

export interface FocusTask extends Pick<Task, "id" | "title" | "status" | "focus_state" | "first_step" | "why" | "energy_level" | "estimated_minutes" | "project_id"> {
  is_anchor?: boolean;
  today_position?: number;
  completed_at?: string | null;
}

export interface TodayPlan {
  day_key: string;
  energy_level: Energy | null;
  tasks: FocusTask[];
}

export interface NowState {
  task: FocusTask | null;
  focus_session: { id: string; task_id: string; duration_minutes: number; started_at: string; status: string } | null;
  day_key: string;
  energy_level: Energy | null;
  empty_state: boolean;
}

export interface CloseState {
  day_key: string;
  done_list: Array<{ id: string; title: string; completed_at?: string }>;
  drift_triggers: DriftTrigger[];
  drift_summary: string | null;
  tomorrow_task_id: string | null;
  reflection: string | null;
}
