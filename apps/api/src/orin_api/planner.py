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
    IntentName.UPDATE_TASK: "update_task",
    IntentName.COMPLETE_TASK: "complete_task",
    IntentName.CREATE_PROJECT: "create_project",
    IntentName.LIST_PROJECTS: "list_projects",
    IntentName.LIST_TASKS: "list_tasks",
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
