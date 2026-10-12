"""Creative Studio domain service.

Holds the business logic for ideas, outlines, document cards, and the
idea-canvas linking. Pure domain logic, no HTTP or presentation concerns,
so it can be unit-tested without a web or database fixture.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from orin_api.models import (
    IdeaInbox,
    CreativeDocumentCard,
    CreativeOutlineItem,
    IdeaDocumentLink,
    KnowledgeDocument,
    Project,
)


@dataclass
class Idea:
    id: uuid.UUID
    title: str
    content: str | None
    document_id: uuid.UUID | None
    status: str
    created_at: datetime
    updated_at: datetime
    linked_document_ids: list[str] = field(default_factory=list)


@dataclass
class OutlineItem:
    id: uuid.UUID
    title: str
    summary: str | None
    kind: str
    status: str
    position: int
    parent_id: uuid.UUID | None
    document_id: uuid.UUID | None


@dataclass
class DocumentCard:
    id: uuid.UUID
    title: str
    summary: str | None
    purpose: str | None
    central_question: str | None
    point_of_view: str | None
    status: str
    position: int


@dataclass
class IdeaDocumentLink:
    idea_id: uuid.UUID
    document_id: uuid.UUID
    link_type: str
    note: str | None


@dataclass
class IdeasCatalog:
    ideas: dict[uuid.UUID, Idea] = field(default_factory=dict)
    links: dict[tuple[uuid.UUID, uuid.UUID], IdeaDocumentLink] = field(
        default_factory=dict
    )

    @property
    def active_ideas(self) -> list[Idea]:
        return [
            idea
            for idea in self.ideas.values()
            if idea.status in ("active", "draft", "review")
        ]

    @property
    def connected_documents(self) -> set[uuid.UUID]:
        return {link.document_id for link in self.links.values()}

    def _to_domain_idea(self, row: IdeaInbox) -> Idea:
        linked = []
        if row.linked_document_ids:
            linked = [item for item in row.linked_document_ids.split(",") if item.strip()]
        return Idea(
            id=row.id,
            title=row.title,
            content=row.content,
            document_id=row.document_id,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
            linked_document_ids=linked,
        )

    def add_idea(
        self,
        *,
        session: Session,
        user_id: uuid.UUID,
        title: str,
        content: str = "",
        document_id: uuid.UUID | None = None,
    ) -> Idea:
        if not title.strip():
            raise ValueError("Idea title must not be empty")
        idea = IdeaInbox(
            id=uuid.uuid4(),
            user_id=user_id,
            title=title.strip(),
            content=content.strip()[:50000],
            document_id=document_id,
            linked_document_ids=",".join(sorted({str(document_id)}) if document_id else ""),
            status="active",
        )
        session.add(idea)
        session.flush()
        self.ideas[idea.id] = self._to_domain_idea(idea)
        return self.ideas[idea.id]

    def link_idea_to_document(self, *, session, idea_id: uuid.UUID, document_id: uuid.UUID, link_type: str = "inspires", note: str = "") -> IdeaDocumentLink:
        key = (idea_id, document_id)
        if key in self.links:
            raise ValueError("This idea is already linked to the document")
        link = IdeaDocumentLink(
            id=uuid.uuid4(),
            user_id=knowledge_document_user_id(session, document_id),
            idea_id=idea_id,
            document_id=document_id,
            link_type=link_type,
            note=note.strip()[:1000] or None,
        )
        row = session.get(IdeaInbox, idea_id)
        if row is None:
            raise ValueError("Idea not found")
        existing = row.linked_document_ids or ""
        if str(document_id) not in existing.split(","):
            row.linked_document_ids = existing + ("," if existing else "") + str(document_id)
        session.add(link)
        session.flush()
        self.links[key] = link
        return link

    def unhook_idea_from_document(self, *, session, idea_id: uuid.UUID, document_id: uuid.UUID) -> None:
        key = (idea_id, document_id)
        link = self.links.pop(key, None)
        if link is None:
            return
        session.delete(link)
        row = session.get(IdeaInbox, idea_id)
        if row is None:
            return
        existing = [item for item in (row.linked_document_ids or "").split(",") if item.strip() and item != str(document_id)]
        row.linked_document_ids = ",".join(existing)

    def outline_items_for_project(self, *, session: Session, project_id: uuid.UUID | None) -> list[OutlineItem]:
        query = select(CreativeOutlineItem).where(CreativeOutlineItem.user_id == session.get(Project, project_id).owner_id if project_id else True)
        if project_id:
            query = query.where(CreativeOutlineItem.project_id == project_id)
        rows = session.scalars(query).all()
        return [self._to_domain_outline_item(row) for row in rows]

    def _to_domain_outline_item(self, row: CreativeOutlineItem) -> OutlineItem:
        return OutlineItem(
            id=row.id,
            title=row.title,
            summary=row.summary,
            kind=row.kind,
            status=row.status,
            position=row.position,
            parent_id=row.parent_id,
            document_id=row.document_id,
        )

    def insert_outline_item(
        self,
        *,
        session: Session,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None,
        parent_id: uuid.UUID | None,
        document_id: uuid.UUID | None,
        title: str,
        summary: str = "",
        kind: str = "section",
        position: int = 0,
    ) -> OutlineItem:
        if not title.strip():
            raise ValueError("Outline item title must not be empty")
        item = CreativeOutlineItem(
            id=uuid.uuid4(),
            user_id=user_id,
            project_id=project_id,
            parent_id=parent_id,
            document_id=document_id,
            title=title.strip(),
            summary=summary.strip()[:2000] or None,
            kind=kind,
            status="planned",
            position=position,
        )
        session.add(item)
        session.flush()
        return self._to_domain_outline_item(item)

    def insert_document_card(
        self,
        *,
        session: Session,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None,
        document_id: uuid.UUID | None,
        title: str,
        summary: str = "",
        purpose: str = "",
        central_question: str = "",
        point_of_view: str = "",
        status: str = "todo",
        position: int = 0,
    ) -> DocumentCard:
        if not title.strip():
            raise ValueError("Card title must not be empty")
        card = CreativeDocumentCard(
            id=uuid.uuid4(),
            user_id=user_id,
            project_id=project_id,
            document_id=document_id,
            title=title.strip(),
            summary=summary.strip()[:2000] or None,
            purpose=purpose.strip()[:2000] or None,
            central_question=central_question.strip()[:500] or None,
            point_of_view=point_of_view.strip()[:240] or None,
            status=status,
            position=position,
        )
        session.add(card)
        session.flush()
        return DocumentCard(
            id=card.id,
            title=card.title,
            summary=card.summary,
            purpose=card.purpose,
            central_question=card.central_question,
            point_of_view=card.point_of_view,
            status=card.status,
            position=card.position,
        )


def knowledge_document_user_id(session: Session, document_id: uuid.UUID) -> uuid.UUID:
    row = session.get(KnowledgeDocument, document_id)
    if row is None:
        raise ValueError("Document not found")
    return row.user_id

