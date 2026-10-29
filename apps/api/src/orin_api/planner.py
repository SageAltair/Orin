"""Translate validated AI intents into registered application actions."""
from dataclasses import dataclass
from typing import Any

from orin_api.ai import AIIntent, IntentName


@dataclass(frozen=True)
class ActionPlan:
    action: str
    inputs: dict[str, Any]
    intent: IntentName


_INTENT_ACTIONS = {
    IntentName.CREATE_TASK: "create_task",
    IntentName.BREAK_DOWN_TASK: "break_down_task",
    IntentName.SET_ENERGY_TODAY: "set_energy_today",
    IntentName.PROPOSE_TODAYS_THREE: "propose_todays_three",
    IntentName.SWAP_TASK: "swap_task",
    IntentName.LOG_DRIFT: "log_drift",
    IntentName.RELEASE_TASK: "release_task",
    IntentName.END_FOCUS_SESSION: "end_focus_session",
    IntentName.RUN_DAILY_CLOSE: "run_daily_close",
    IntentName.UPDATE_TASK: "update_task",
    IntentName.COMPLETE_TASK: "complete_task",
    IntentName.CREATE_PROJECT: "create_project",
    IntentName.LIST_PROJECTS: "list_projects",
    IntentName.LIST_TASKS: "list_tasks",
    IntentName.LIST_CALENDAR: "list_calendar",
    IntentName.FIND_FREE_TIME: "find_free_time",
    IntentName.SCHEDULE_TASK: "schedule_task",
    IntentName.UNSCHEDULE_TASK: "unschedule_task",
    IntentName.CREATE_CALENDAR_EVENT: "create_calendar_event",
    IntentName.UPDATE_CALENDAR_EVENT: "update_calendar_event",
    IntentName.DELETE_CALENDAR_EVENT: "delete_calendar_event",
    IntentName.GET_ACTIVITY: "get_activity",
    IntentName.WORKER_ACTION: "request_worker_action",
    IntentName.SAVE_MEMORY: "save_memory",
    IntentName.START_FOCUS: "start_focus_session",
    IntentName.SET_TOOL_VISIBILITY: "set_tool_visibility",
}


def plan_intent(proposal: AIIntent) -> ActionPlan | None:
    action = _INTENT_ACTIONS.get(proposal.intent)
    if action is None:
        return None
    return ActionPlan(action=action, inputs=proposal.parameters.model_dump(exclude_none=True, mode="python"), intent=proposal.intent)
