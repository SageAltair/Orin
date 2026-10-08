"""Translate validated model proposals into the application's explicit action set."""
from dataclasses import dataclass

from orin_api.ai import AIIntent, IntentName, IntentParameters


@dataclass(frozen=True)
class ActionPlan:
    intent: IntentName
    parameters: IntentParameters


_SUPPORTED_ACTIONS = {
    IntentName.CREATE_TASK,
    IntentName.UPDATE_TASK,
    IntentName.COMPLETE_TASK,
    IntentName.CREATE_PROJECT,
    IntentName.LIST_PROJECTS,
    IntentName.LIST_TASKS,
    IntentName.GET_ACTIVITY,
}


def plan_intent(proposal: AIIntent) -> ActionPlan | None:
    """Return a plan only for explicitly supported application actions."""
    if proposal.intent not in _SUPPORTED_ACTIONS:
        return None
    return ActionPlan(intent=proposal.intent, parameters=proposal.parameters)
