"""Evidence-backed product context available to Orin's command interpreter.

Keep this inventory aligned with the real web entry points and API routers. It
deliberately describes runtime capabilities and inspection limits separately.
"""
from __future__ import annotations

import re
from collections.abc import Sequence


PRODUCT_INVENTORY = {
    "status_definitions": {
        "implemented": "Present in the cited application code; this label alone does not mean manually interaction-tested.",
        "partially implemented": "Some supporting code exists, but the cited product surface or workflow is incomplete.",
        "planned": "Only use when a maintained roadmap explicitly identifies the capability as planned.",
        "disabled": "Implemented but currently switched off by configuration or product policy.",
        "unverified": "Evidence is insufficient to confirm implementation or working behavior.",
    },
    "identity": {
        "name": "Orin",
        "purpose": "A personal workspace for organizing projects, tasks, priorities, and work conversations.",
        "target_users": "People coordinating their own projects and next actions.",
        "identity_source": "apps/web/src/App.tsx and apps/api/src/orin_api/main.py",
    },
    "screens": [
        {"name": "Home", "status": "implemented", "evidence": "App.tsx: workspace greeting, open tasks, recent sessions, active projects, empty states"},
        {"name": "Projects", "status": "implemented", "evidence": "ProjectWorkspace.tsx; project API routes"},
        {"name": "Tasks", "status": "implemented", "evidence": "App.tsx task list/editor; task API routes"},
        {"name": "Activity", "status": "implemented", "evidence": "ActivityTimeline.tsx; activity API routes"},
        {"name": "Settings", "status": "implemented", "evidence": "AccountSecurity, DeviceSettings, WorkspaceSettings, GitHubSettings, preferences"},
        {"name": "Ask Orin drawer", "status": "implemented", "evidence": "App.tsx; commands, conversation history/search, attachments, project/task context"},
    ],
    "capabilities": [
        {"name": "Projects and tasks", "status": "implemented", "evidence": "web forms and API CRUD routes; PostgreSQL models"},
        {"name": "Conversation history and search", "status": "implemented", "evidence": "conversation and command API; Ask Orin history/search panels"},
        {"name": "Task and project context in conversations", "status": "implemented", "evidence": "conversation context assembly in domain_router.py"},
        {"name": "Attachments", "status": "implemented", "evidence": "attachment_router.py and Ask Orin upload/render flow; image analysis depends on configured vision model"},
        {"name": "Activity history", "status": "implemented", "evidence": "activity API and ActivityTimeline.tsx"},
        {"name": "Personal memories and focus sessions", "status": "partially implemented", "evidence": "workspace_router.py APIs and context retrieval; no dedicated primary navigation screen in capabilities.ts"},
        {"name": "Account and workspace preferences", "status": "implemented", "evidence": "Settings components and workspace API"},
        {"name": "GitHub connection", "status": "implemented, configuration-dependent", "evidence": "GitHubSettings.tsx and integration_router.py; requires configured OAuth credentials and user connection"},
        {"name": "Computer worker actions", "status": "implemented, permission and device-dependent", "evidence": "worker_router.py and worker app; queued actions use approval and an enrolled worker"},
        {"name": "AI interpretation", "status": "implemented, configuration-dependent", "evidence": "AI providers in ai.py; requires valid provider credentials and model"},
    ],
    "boundaries": [
        "No roadmap source is included in the supplied product inventory, so no feature is asserted as planned.",
        "There is no live browser/DOM/screenshot access in this command path; do not claim to see the user's current screen.",
        "This API receives a bounded workspace snapshot and attached file content, not arbitrary repository access at runtime.",
        "Routes/components listed here establish declared implementation, not successful execution of every interaction.",
        "Authentication scopes private workspace records to the signed-in user; worker actions are permission/approval gated.",
        "No audit history or report persistence feature is present; recommendations remain conversational unless the user requests a supported change.",
    ],
}

_SELF_REFERENCE = re.compile(
    r"\b(?:orin\b|this\s+(?:app|application|system|product|interface|ui)\b|"
    r"the\s+(?:app|application|system|interface)\s+(?:i'?m|i\s+am)\s+using\b|"
    r"your\s+(?:interface|app|application|ui)\b|current\s+(?:ui|screen|application)\b|"
    r"what\s+should\s+be\s+improved\s+here\b)", re.IGNORECASE)
_AUDIT_REQUEST = re.compile(r"\b(review|audit|evaluate|assess|inspect|look\s+at|examine|usability|ui/?ux)\b", re.IGNORECASE)


def needs_product_context(message: str, recent_user_messages: Sequence[str]) -> bool:
    """Resolve an app review to Orin using current and recent user context."""
    recent_text = "\n".join(recent_user_messages[-6:])
    if _SELF_REFERENCE.search(message):
        return True
    return bool(_AUDIT_REQUEST.search(message) and _SELF_REFERENCE.search(recent_text))


def product_context_for_prompt() -> str:
    """Return compact, JSON-serializable, implementation-grounded product facts."""
    import json

    return json.dumps(PRODUCT_INVENTORY, ensure_ascii=True, separators=(",", ":"))
