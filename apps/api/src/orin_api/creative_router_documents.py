"""Creative Studio API routes: project outline and document cards."""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from orin_api.auth import get_current_user
from orin_api.database import get_session
from orin_api.models import (
    ActivityType,
    CreativeDocumentCard,
    CreativeOutlineItem,
    KnowledgeDocument,
    Project,
    User,
)
from orin_api.services import add_activity

router = APIRouter(prefix="/api/v1/creative", tags=["creative studio"])


def _owned_project(session: Session, project_id: uuid.UUID, user: User) -> Project:
    project = session.get(Project, project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _owned_document(session: Session, document_id: uuid.UUID | None, project_id: uuid.UUID, user: User) -> None:
    if document_id is None:
        return
    document = session.scalar(select(KnowledgeDocument).where(
        KnowledgeDocument.id == document_id, KnowledgeDocument.user_id == user.id
    ))
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.project_id is not None and document.project_id != project_id:
        raise HTTPException(status_code=422, detail="Document belongs to another project")


class OutlineItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parent_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=240)
    summary: str | None = None
    kind: Literal[
        "section", "chapter", "scene", "verse", "stanza", "beat", "act", "note"
    ] = "section"
    position: int = 0


class OutlineItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    parent_id: uuid.UUID | None
    document_id: uuid.UUID | None
    title: str
    summary: str | None
    kind: str
    status: str
    position: int
    created_at: str
    updated_at: str


class OutlineItemPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=240)
    summary: str | None = None
    status: Literal["planned", "drafted", "revised", "done"] | None = None
    position: int | None = None


class DocumentCardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=240)
    summary: str | None = None
    purpose: str | None = None
    central_question: str | None = None
    point_of_view: str | None = None
    status: Literal[
        "todo", "drafting", "revised", "polished", "ready", "published"
    ] = "todo"
    position: int = 0


class DocumentCardPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=240)
    summary: str | None = None
    purpose: str | None = None
    central_question: str | None = None
    point_of_view: str | None = None
    document_id: uuid.UUID | None = None
    status: Literal["todo", "drafting", "revised", "polished", "ready", "published"] | None = None
    position: int | None = None


class DocumentCardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID | None
    document_id: uuid.UUID | None
    title: str
    summary: str | None
    purpose: str | None
    central_question: str | None
    point_of_view: str | None
    status: str
    position: int
    created_at: str
    updated_at: str


def _outline_view(row: CreativeOutlineItem) -> OutlineItemRead:
    return OutlineItemRead(
        id=row.id,
        parent_id=row.parent_id,
        document_id=row.document_id,
        title=row.title,
        summary=row.summary,
        kind=row.kind,
        status=row.status,
        position=row.position,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _card_view(row: CreativeDocumentCard) -> DocumentCardRead:
    return DocumentCardRead(
        id=row.id,
        project_id=row.project_id,
        document_id=row.document_id,
        title=row.title,
        summary=row.summary,
        purpose=row.purpose,
        central_question=row.central_question,
        point_of_view=row.point_of_view,
        status=row.status,
        position=row.position,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


@router.get("/projects/{project_id}/outline", response_model=list[OutlineItemRead])
def list_outline_items(
    project_id: uuid.UUID,
    parent_id: uuid.UUID | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[OutlineItemRead]:
    _owned_project(session, project_id, user)
    query = select(CreativeOutlineItem).where(CreativeOutlineItem.project_id == project_id)
    if parent_id is not None:
        query = query.where(CreativeOutlineItem.parent_id == parent_id)
    rows = session.scalars(query.order_by(CreativeOutlineItem.position)).all()
    return [_outline_view(row) for row in rows]


@router.post("/projects/{project_id}/outline", response_model=OutlineItemRead, status_code=status.HTTP_201_CREATED)
def create_outline_item(
    project_id: uuid.UUID,
    payload: OutlineItemCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> OutlineItemRead:
    _owned_project(session, project_id, user)
    if payload.parent_id is not None and payload.document_id is not None:
        raise HTTPException(status_code=422, detail="Provide only one of parent_id or document_id")
    _owned_document(session, payload.document_id, project_id, user)
    if payload.parent_id is not None:
        parent = session.get(CreativeOutlineItem, payload.parent_id)
        if parent is None or parent.user_id != user.id or parent.project_id != project_id:
            raise HTTPException(status_code=404, detail="Parent outline item not found")
    row = CreativeOutlineItem(
        id=uuid.uuid4(),
        user_id=user.id,
        project_id=project_id,
        parent_id=payload.parent_id,
        document_id=payload.document_id,
        title=payload.title,
        summary=payload.summary,
        kind=payload.kind,
        status="planned",
        position=payload.position,
    )
    session.add(row)
    session.flush()
    add_activity(
        session,
        user_id=user.id,
        actor_user_id=user.id,
        activity_type=ActivityType.OUTLINE_ITEM_CREATED,
        summary=f"Created {payload.kind}: {payload.title}",
        project_id=project_id,
        metadata={"entity_type": "outline_item", "entity_id": str(row.id)},
        source="api",
    )
    session.commit()
    return _outline_view(row)


@router.patch("/projects/{project_id}/outline/{item_id}", response_model=OutlineItemRead)
def update_outline_item(
    project_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: OutlineItemPatch,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> OutlineItemRead:
    _owned_project(session, project_id, user)
    row = session.get(CreativeOutlineItem, item_id)
    if row is None or row.project_id != project_id or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Outline item not found")
    if payload.title is not None:
        row.title = payload.title
    if "summary" in payload.model_fields_set:
        row.summary = payload.summary
    if payload.status is not None:
        row.status = payload.status
    if payload.position is not None:
        row.position = payload.position
    session.flush()
    add_activity(
        session,
        user_id=user.id,
        actor_user_id=user.id,
        activity_type=ActivityType.OUTLINE_ITEM_UPDATED,
        summary=f"Updated {row.kind}: {row.title}",
        project_id=project_id,
        metadata={"entity_type": "outline_item", "entity_id": str(row.id)},
        source="api",
    )
    session.commit()
    return _outline_view(row)




@router.get("/projects/{project_id}/cards", response_model=list[DocumentCardRead])
def list_document_cards(
    project_id: uuid.UUID,
    card_status: str | None = Query(default=None, alias="status", pattern="^(todo|drafting|revised|polished|ready|published|all)$"),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[DocumentCardRead]:
    _owned_project(session, project_id, user)
    query = select(CreativeDocumentCard).where(CreativeDocumentCard.project_id == project_id)
    if card_status is not None and card_status != "all":
        query = query.where(CreativeDocumentCard.status == card_status)
    rows = session.scalars(query.order_by(CreativeDocumentCard.position)).all()
    return [_card_view(row) for row in rows]


@router.post("/projects/{project_id}/cards", response_model=DocumentCardRead, status_code=status.HTTP_201_CREATED)
def create_document_card(
    project_id: uuid.UUID,
    payload: DocumentCardCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DocumentCardRead:
    _owned_project(session, project_id, user)
    _owned_document(session, payload.document_id, project_id, user)
    if payload.project_id is not None and payload.project_id != project_id:
        raise HTTPException(status_code=422, detail="Project does not match the URL")
    row = CreativeDocumentCard(
        id=uuid.uuid4(),
        user_id=user.id,
        project_id=project_id,
        document_id=payload.document_id,
        title=payload.title,
        summary=payload.summary,
        purpose=payload.purpose,
        central_question=payload.central_question,
        point_of_view=payload.point_of_view,
        status=payload.status,
        position=payload.position,
    )
    session.add(row)
    session.flush()
    add_activity(
        session,
        user_id=user.id,
        actor_user_id=user.id,
        activity_type=ActivityType.DOCUMENT_CARD_CREATED,
        summary=f"Created card: {payload.title}",
        project_id=project_id,
        metadata={"entity_type": "card", "entity_id": str(row.id)},
        source="api",
    )
    session.commit()
    return _card_view(row)



@router.patch("/projects/{project_id}/cards/{card_id}", response_model=DocumentCardRead)
def update_document_card(
    project_id: uuid.UUID,
    card_id: uuid.UUID,
    payload: DocumentCardPatch,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DocumentCardRead:
    _owned_project(session, project_id, user)
    card = session.get(CreativeDocumentCard, card_id)
    if card is None or card.project_id != project_id or card.user_id != user.id:
        raise HTTPException(status_code=404, detail="Card not found")
    _owned_document(session, payload.document_id, project_id, user)
    changes = payload.model_dump(exclude_unset=True)
    if any(changes.get(key) is None for key in ("title", "status", "position") if key in changes):
        raise HTTPException(status_code=422, detail="Title, status and position cannot be null")
    for key, value in changes.items():
        setattr(card, key, value)
    session.flush()
    add_activity(
        session,
        user_id=user.id,
        actor_user_id=user.id,
        activity_type=ActivityType.DOCUMENT_CARD_UPDATED,
        summary=f"Updated card: {card.title}",
        project_id=project_id,
        metadata={"entity_type": "card", "entity_id": str(card.id)},
        source="api",
    )
    session.commit()
    return _card_view(card)
