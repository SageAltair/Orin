from __future__ import annotations

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from orin_api.auth import get_current_user
from orin_api.database import get_session
from orin_api.models import AssistantTemplate, User

router = APIRouter(prefix="/api/v1/intelligence/templates", tags=["intelligence"])
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
PromptText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
PageName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40, pattern=r"^[a-z_]+$")]

SYSTEM_TEMPLATES = (
    ("plan-new-project", "Plan a New Project", "Projects", "Turn an outcome into a practical project plan.", "Help me plan a new project. Clarify the outcome, phases, milestones, tasks, dependencies, risks, and first next action. Use the selected project when relevant.", ["projects", "home"]),
    ("organize-day", "Organize My Day", "Planning", "Choose a realistic plan for today.", "Organize my day using my tasks, calendar, energy, deadlines, and current commitments. Recommend no more than three priorities and explain tradeoffs.", ["home", "tasks", "calendar", "focus"]),
    ("plan-week", "Plan My Week", "Planning", "Build a balanced weekly plan.", "Plan my week around deadlines, calendar commitments, project priorities, focus time, and recovery. Flag conflicts before proposing changes.", ["home", "calendar"]),
    ("brain-dump", "Brain Dump to Tasks", "Tasks", "Convert unstructured thoughts into useful actions.", "Organize my brain dump into projects, tasks, reminders, decisions, and reference notes. Show a preview and ask only for information required to execute changes.", ["home", "tasks"]),
    ("project-health", "Project Health Check", "Projects", "Review progress, blockers, dependencies, and risks.", "Run a health check on the selected project. Review objectives, progress, overdue work, dependencies, blockers, risks, and the next useful action. Base every finding on workspace evidence.", ["projects"]),
    ("review-writing", "Review My Writing", "Writing", "Give focused feedback on the current document.", "Review the current writing for structure, clarity, evidence, tone, and unfinished sections. Preserve my voice and prioritize the three most useful improvements.", ["writing", "memories"]),
    ("develop-idea", "Develop an Idea", "Writing", "Turn an early idea into a stronger concept.", "Develop the selected idea. Identify its core promise, audience, useful connections, open questions, and one concrete next step.", ["writing", "memories", "home"]),
    ("what-missing", "What Am I Missing?", "Risks", "Find overlooked commitments, dependencies, and risks.", "Review the current authorized context for overlooked commitments, missing dependencies, unresolved decisions, conflicts, neglected opportunities, and risks. Return a short prioritized list with evidence and next actions.", ["home", "projects", "tasks", "calendar"]),
    ("project-risks", "Analyze Project Risks", "Risks", "Identify and prioritize project risks.", "Analyze risks for the selected project. Separate confirmed issues from possible concerns, cite the supporting workspace context, and suggest proportionate mitigations.", ["projects"]),
    ("review-progress", "Review My Progress", "Reflection", "Summarize meaningful progress and next steps.", "Review my recent progress using completed work, advanced projects, resolved blockers, decisions, and missed commitments. Avoid generic motivation and suggest one useful next move.", ["home", "activity", "focus"]),
)


class TemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: ShortText
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    category: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    prompt: PromptText
    compatible_pages: list[PageName] = Field(default_factory=list, max_length=12)


class TemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: ShortText | None = None
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)] | None = None
    category: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)] | None = None
    prompt: PromptText | None = None
    compatible_pages: list[PageName] | None = Field(default=None, max_length=12)
    is_favorite: bool | None = None
    is_pinned: bool | None = None


def _seed(session: Session, user_id: uuid.UUID) -> None:
    existing = set(session.scalars(select(AssistantTemplate.slug).where(
        AssistantTemplate.user_id == user_id, AssistantTemplate.is_system.is_(True))).all())
    for slug, title, category, description, prompt, pages in SYSTEM_TEMPLATES:
        if slug not in existing:
            session.add(AssistantTemplate(user_id=user_id, slug=slug, title=title, category=category,
                description=description, prompt=prompt, compatible_pages=pages, is_system=True))
    session.flush()


def _read(row: AssistantTemplate) -> dict[str, object]:
    return {"id": row.id, "slug": row.slug, "title": row.title, "description": row.description,
            "category": row.category, "prompt": row.prompt, "compatible_pages": row.compatible_pages,
            "is_system": row.is_system, "is_favorite": row.is_favorite, "is_pinned": row.is_pinned,
            "updated_at": row.updated_at}


@router.get("")
def list_templates(search: str = Query(default="", max_length=120), category: str | None = Query(default=None, max_length=40),
                   page: str | None = Query(default=None, max_length=40), user: User = Depends(get_current_user),
                   session: Session = Depends(get_session)) -> list[dict[str, object]]:
    try:
        _seed(session, user.id)
    except IntegrityError:
        # Concurrent first visits can both attempt to install the same defaults.
        session.rollback()
    query = select(AssistantTemplate).where(AssistantTemplate.user_id == user.id)
    if search.strip():
        value = f"%{search.strip()}%"
        query = query.where(or_(AssistantTemplate.title.ilike(value), AssistantTemplate.description.ilike(value),
                                AssistantTemplate.category.ilike(value)))
    if category:
        query = query.where(AssistantTemplate.category == category)
    rows = session.scalars(query.order_by(AssistantTemplate.is_pinned.desc(), AssistantTemplate.is_favorite.desc(),
                                          AssistantTemplate.category, AssistantTemplate.title)).all()
    if page:
        rows = [row for row in rows if not row.compatible_pages or page in row.compatible_pages]
    session.commit()
    return [_read(row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_template(data: TemplateCreate, user: User = Depends(get_current_user),
                    session: Session = Depends(get_session)) -> dict[str, object]:
    base = re.sub(r"[^a-z0-9]+", "-", data.title.casefold()).strip("-")[:70] or "template"
    slug = f"custom-{base}-{uuid.uuid4().hex[:8]}"
    row = AssistantTemplate(user_id=user.id, slug=slug, **data.model_dump())
    session.add(row)
    session.commit()
    session.refresh(row)
    return _read(row)


@router.patch("/{template_id}")
def update_template(template_id: uuid.UUID, data: TemplateUpdate, user: User = Depends(get_current_user),
                    session: Session = Depends(get_session)) -> dict[str, object]:
    row = session.scalar(select(AssistantTemplate).where(
        AssistantTemplate.id == template_id, AssistantTemplate.user_id == user.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    changes = data.model_dump(exclude_unset=True)
    if row.is_system and any(key not in {"is_favorite", "is_pinned"} for key in changes):
        raise HTTPException(status_code=409, detail="Built-in template content cannot be edited.")
    for key, value in changes.items():
        setattr(row, key, value)
    session.commit()
    return _read(row)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: uuid.UUID, user: User = Depends(get_current_user),
                    session: Session = Depends(get_session)) -> Response:
    row = session.scalar(select(AssistantTemplate).where(
        AssistantTemplate.id == template_id, AssistantTemplate.user_id == user.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    if row.is_system:
        raise HTTPException(status_code=409, detail="Built-in templates cannot be deleted.")
    session.delete(row)
    session.commit()
    return Response(status_code=204)
