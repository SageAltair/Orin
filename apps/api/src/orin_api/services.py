from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from orin_api.models import (
    Activity,
    ActivityType,
    Capability,
    Project,
    ProjectMember,
    ProjectRole,
    User,
    UserCapability,
    UserPreferences,
)
from orin_api.schemas import PreferencesUpdate


CAPABILITY_CATALOG = (
    ("home", "Home", "Your current priorities"),
    ("projects", "Projects", "Organize work by outcome"),
    ("tasks", "Tasks", "Keep track of next steps"),
    ("activity", "Activity", "A record of recent changes"),
    ("settings", "Settings", "Shape your Orin workspace"),
)


def require_user(session: Session, user_id: uuid.UUID) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def ensure_capability_catalog(session: Session) -> list[Capability]:
    existing = {capability.code: capability for capability in session.scalars(select(Capability)).all()}
    changed = False
    for code, name, description in CAPABILITY_CATALOG:
        if code not in existing:
            capability = Capability(code=code, name=name, description=description)
            session.add(capability)
            existing[code] = capability
            changed = True
    if changed:
        session.flush()
    return [existing[code] for code, _, _ in CAPABILITY_CATALOG]


def ensure_user_preferences(session: Session, user: User) -> UserPreferences:
    catalog = ensure_capability_catalog(session)
    preferences = session.scalar(select(UserPreferences).where(UserPreferences.user_id == user.id))
    if preferences is None:
        preferences = UserPreferences(user_id=user.id)
        session.add(preferences)
    assigned = {
        capability_id
        for capability_id in session.scalars(
            select(UserCapability.capability_id).where(UserCapability.user_id == user.id)
        ).all()
    }
    for capability in catalog:
        if capability.id not in assigned:
            visible = capability.is_enabled and capability.code in {"home", "tasks"}
            session.add(UserCapability(
                user_id=user.id,
                capability_id=capability.id,
                granted=capability.is_enabled,
                visible=visible,
                pinned=visible,
            ))
    session.flush()
    return preferences


def preference_view(session: Session, user: User, preferences: UserPreferences) -> dict[str, object]:
    rows = session.execute(
        select(Capability.code, Capability.is_enabled, UserCapability.granted, UserCapability.visible, UserCapability.pinned)
        .join(UserCapability, UserCapability.capability_id == Capability.id)
        .where(UserCapability.user_id == user.id)
        .order_by(Capability.code)
    ).all()
    return {
        "density": preferences.density,
        "theme": preferences.theme,
        "locale": preferences.locale,
        "visible_capabilities": [row.code for row in rows if row.visible and row.granted and row.is_enabled],
        "hidden_capabilities": [row.code for row in rows if row.granted and not row.visible and row.is_enabled],
        "pinned_capabilities": [row.code for row in rows if row.pinned and row.visible and row.granted and row.is_enabled],
    }


def update_preferences(session: Session, user: User, data: PreferencesUpdate) -> UserPreferences:
    preferences = ensure_user_preferences(session, user)
    rows = session.execute(
        select(Capability, UserCapability)
        .join(UserCapability, UserCapability.capability_id == Capability.id)
        .where(UserCapability.user_id == user.id)
    ).all()
    assignments = {capability.code: (capability, assignment) for capability, assignment in rows}
    requested_visible = set(data.visible_capabilities)
    requested_pinned = set(data.pinned_capabilities)
    unknown = (requested_visible | requested_pinned) - assignments.keys()
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown capability: {sorted(unknown)[0]}")
    unavailable = {
        code
        for code in requested_visible | requested_pinned
        if not assignments[code][0].is_enabled or not assignments[code][1].granted
    }
    if unavailable:
        raise HTTPException(status_code=422, detail=f"Capability is not granted: {sorted(unavailable)[0]}")
    if requested_pinned - requested_visible:
        raise HTTPException(status_code=422, detail="Pinned capabilities must also be visible")
    for code, (_, assignment) in assignments.items():
        assignment.visible = assignment.granted and code in requested_visible
        assignment.pinned = assignment.visible and code in requested_pinned
    preferences.density = data.density
    preferences.theme = data.theme
    preferences.locale = data.locale
    session.flush()
    return preferences


def add_activity(
    session: Session,
    *,
    user_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    activity_type: ActivityType,
    summary: str,
    project_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
) -> None:
    session.add(Activity(
        user_id=user_id,
        actor_user_id=actor_user_id,
        activity_type=activity_type,
        summary=summary,
        project_id=project_id,
        task_id=task_id,
    ))


def add_project_owner_membership(session: Session, project: Project) -> None:
    session.add(ProjectMember(project_id=project.id, user_id=project.owner_id, role=ProjectRole.OWNER))
