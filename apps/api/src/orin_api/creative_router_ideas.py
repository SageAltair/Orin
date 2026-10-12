"""Creative Studio API routes: ideas, links, and the idea canvas."""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from orin_api.auth import get_current_user
from orin_api.database import get_session
from orin_api.models import (
    ActivityType,
    IdeaDocumentLink,
    IdeaInbox,
    KnowledgeDocument,
    User,
)
from orin_api.services import add_activity

router = APIRouter(prefix="/api/v1/creative", tags=["creative studio"])


class StudioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=20000)


class IdeaInboxItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    content: str | None
    document_id: uuid.UUID | None
    status: str
    linked_document_ids: list[str] = Field(default_factory=list)


class IdeaLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: uuid.UUID
    link_type: Literal["inspires", "contrasts", "extends", "supports"] = "inspires"
    note: str | None = None


class IdeaLink(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    idea_id: uuid.UUID
    document_id: uuid.UUID
    link_type: str
    note: str | None


def _idea_view(idea: IdeaInbox) -> IdeaInboxItem:
    linked = [part for part in (idea.linked_document_ids or "").split(",") if part.strip()]
    return IdeaInboxItem(
        id=idea.id,
        title=idea.title,
        content=idea.content,
        document_id=idea.document_id,
        status=idea.status,
        linked_document_ids=linked,
    )



@router.post("/ideas", response_model=IdeaInboxItem, status_code=status.HTTP_201_CREATED)
def create_idea(
    payload: StudioRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> IdeaInboxItem:
    title = payload.text.split("\n")[0].strip()[:240] or "Untitled idea"
    idea = IdeaInbox(
        id=uuid.uuid4(),
        user_id=user.id,
        title=title,
        content=payload.text[:50000],
        status="active",
        linked_document_ids="",
    )
    session.add(idea)
    session.flush()
    add_activity(
        session,
        user_id=user.id,
        actor_user_id=user.id,
        activity_type=ActivityType.IDEA_CREATED,
        summary=f"Captured idea: {idea.title}",
        metadata={"entity_type": "idea", "entity_id": str(idea.id)},
        source="api",
    )
    session.commit()
    return _idea_view(idea)


@router.get("/ideas", response_model=list[IdeaInboxItem])
def list_ideas(
    idea_status: str | None = Query(default=None, alias="status", pattern="^(active|archived|all)$"),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[IdeaInboxItem]:
    query = select(IdeaInbox).where(IdeaInbox.user_id == user.id)
    if idea_status == "active":
        query = query.where(IdeaInbox.status == "active")
    elif idea_status == "archived":
        query = query.where(IdeaInbox.status == "archived")
    rows = session.scalars(query.order_by(IdeaInbox.updated_at.desc()).limit(limit)).all()
    return [_idea_view(row) for row in rows]


@router.patch("/ideas/{idea_id}", response_model=IdeaInboxItem)
def update_idea(
    idea_id: uuid.UUID,
    payload: StudioRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> IdeaInboxItem:
    row = session.get(IdeaInbox, idea_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Idea not found")
    row.title = payload.text.split("\n")[0].strip()[:240] or row.title
    row.content = payload.text[:50000]
    session.flush()
    session.commit()
    return _idea_view(row)

@router.post("/ideas/{idea_id}/links", response_model=IdeaLink)
def create_idea_link(
    idea_id: uuid.UUID,
    payload: IdeaLinkCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> IdeaLink:
    idea = session.get(IdeaInbox, idea_id)
    if idea is None or idea.user_id != user.id:
        raise HTTPException(status_code=404, detail="Idea not found")
    document = session.get(KnowledgeDocument, payload.document_id)
    if document is None or document.user_id != user.id:
        raise HTTPException(status_code=404, detail="Document not found")
    existing = session.scalar(
        select(IdeaDocumentLink).where(
            IdeaDocumentLink.idea_id == idea_id,
            IdeaDocumentLink.document_id == payload.document_id,
            IdeaDocumentLink.link_type == payload.link_type,
        )
    )
    if existing is not None:
        link = existing
    else:
        link = IdeaDocumentLink(
            id=uuid.uuid4(),
            user_id=user.id,
            idea_id=idea_id,
            document_id=payload.document_id,
            link_type=payload.link_type,
            note=payload.note or None,
        )
        session.add(link)
    session.flush()
    _sync_linked_documents(session, idea)
    add_activity(
        session,
        user_id=user.id,
        actor_user_id=user.id,
        activity_type=ActivityType.IDEA_LINKED,
        summary=f"Linked {document.title} to idea '{idea.title}'",
        metadata={"entity_type": "idea_link", "entity_id": str(link.id)},
        source="api",
    )
    session.commit()
    return link


@router.get("/ideas/{idea_id}/links", response_model=list[IdeaLink])
def list_idea_links(
    idea_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[IdeaLink]:
    row = session.get(IdeaInbox, idea_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Idea not found")
    links = session.scalars(
        select(IdeaDocumentLink)
        .where(IdeaDocumentLink.idea_id == idea_id)
        .order_by(IdeaDocumentLink.created_at.desc())
    ).all()
    return links


@router.delete("/ideas/{idea_id}/links/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None)
def delete_idea_link(
    idea_id: uuid.UUID,
    document_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    link = session.scalar(
        select(IdeaDocumentLink).where(
            IdeaDocumentLink.idea_id == idea_id,
            IdeaDocumentLink.document_id == document_id,
        )
    )
    if link is None or link.user_id != user.id:
        raise HTTPException(status_code=404, detail="Link not found")
    link_id = link.id
    session.delete(link)
    session.flush()
    idea = session.get(IdeaInbox, idea_id)
    if idea is not None:
        _sync_linked_documents(session, idea)
    add_activity(
        session,
        user_id=user.id,
        actor_user_id=user.id,
        activity_type=ActivityType.IDEA_UNLINKED,
        summary=f"Unlinked document #{document_id} from idea '{idea_id}'",
        metadata={"entity_type": "idea_link", "entity_id": str(link_id)},
        source="api",
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _sync_linked_documents(session: Session, idea: IdeaInbox) -> None:
    ids = session.scalars(
        select(IdeaDocumentLink.document_id).where(IdeaDocumentLink.idea_id == idea.id)
    ).all()
    idea.linked_document_ids = ",".join(sorted(str(item) for item in ids))

