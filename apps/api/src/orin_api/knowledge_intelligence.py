"""Deterministic, evidence-linked knowledge patterns and review eligibility."""
from __future__ import annotations

import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from orin_api.models import KnowledgeDocument, KnowledgeInsight, KnowledgeReview

STOP_WORDS = frozenset("about after again also because before being between could did does doing down each from have here into just more most only other should some such than that their them then there these they this those through under until very what when where which while with would your".split())
TOKEN = re.compile(r"[a-zA-Z][a-zA-Z0-9'-]{3,}")


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def evaluate_knowledge(session: Session, user_id: uuid.UUID, *, now: datetime | None = None) -> dict[str, int]:
    """Refresh rule-based topic insights and eligible reviews without AI or external calls."""
    current = now or datetime.now(timezone.utc)
    docs = session.scalars(select(KnowledgeDocument).where(
        KnowledgeDocument.user_id == user_id,
        KnowledgeDocument.archived.is_(False),
        KnowledgeDocument.exclude_from_ai.is_(False),
        KnowledgeDocument.document_type != "journal",
    ).order_by(KnowledgeDocument.updated_at.desc()).limit(500)).all()
    topic_documents: dict[str, list[KnowledgeDocument]] = defaultdict(list)
    for doc in docs:
        terms = {term.casefold() for term in TOKEN.findall(f"{doc.title} {doc.content} {' '.join(doc.tags)}") if term.casefold() not in STOP_WORDS}
        for term in terms:
            topic_documents[term].append(doc)

    created_insights = 0
    for term, sources in sorted(topic_documents.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(sources) < 3:
            continue
        total_count = len(sources)
        sources = sorted(sources, key=lambda item: _utc(item.updated_at), reverse=True)[:10]
        fingerprint = f"topic:{term}"[:160]
        insight = session.scalar(select(KnowledgeInsight).where(
            KnowledgeInsight.user_id == user_id,
            KnowledgeInsight.insight_type == "recurring_topic",
            KnowledgeInsight.fingerprint == fingerprint,
        ))
        if insight is not None and insight.status in {"dismissed", "resolved"}:
            continue
        evidence = [{"document_id": str(doc.id), "title": doc.title, "updated_at": doc.updated_at.isoformat()} for doc in sources]
        oldest = min(_utc(doc.updated_at) for doc in sources)
        newest = max(_utc(doc.updated_at) for doc in sources)
        explanation = f"The term “{term}” appears in {total_count} distinct documents. This is a count of matching text, not a claim about its importance."
        if insight is None:
            insight = KnowledgeInsight(user_id=user_id, insight_type="recurring_topic", fingerprint=fingerprint,
                title=f"Recurring topic: {term}", explanation=explanation, evidence=evidence,
                frequency=total_count, confidence=0.55,
                limitations="Keyword overlap can reflect quoted material or unrelated uses of the same word.",
                suggested_next_step="Review the linked documents and connect them if the topic is meaningful.",
                window_start=oldest, window_end=newest, status="active", evaluated_at=current)
            session.add(insight)
            created_insights += 1
        else:
            insight.explanation = explanation
            insight.evidence = evidence
            insight.frequency = total_count
            insight.window_start, insight.window_end = oldest, newest
            insight.evaluated_at = current
            if insight.status == "snoozed" and insight.snoozed_until and _utc(insight.snoozed_until) <= _utc(current):
                insight.status, insight.snoozed_until = "active", None

    review_count = 0
    by_document = {doc.id: doc for doc in session.scalars(select(KnowledgeDocument).where(KnowledgeDocument.user_id == user_id)).all()}
    for doc in by_document.values():
        review = session.scalar(select(KnowledgeReview).where(KnowledgeReview.document_id == doc.id, KnowledgeReview.user_id == user_id))
        eligible_status = doc.status not in {"completed", "parked", "abandoned"} and not doc.archived
        updated_at = _utc(doc.updated_at)
        review_at = _utc(doc.review_at) if doc.review_at else None
        draft_due = doc.document_type == "draft" and doc.status in {"developing", "ready_to_resume"} and updated_at <= current - timedelta(days=7)
        explicit_due = review_at is not None and review_at <= current
        if not eligible_status:
            if review is not None and review.status in {"pending", "snoozed"}:
                review.status, review.snoozed_until = "resolved", None
            continue
        if not (draft_due or explicit_due):
            if review is not None and review.status in {"pending", "snoozed"}:
                # Meaningful edits or a changed review date reset the eligibility clock.
                next_due = review_at or updated_at + timedelta(days=7)
                if next_due > current:
                    review.status, review.due_at, review.snoozed_until = "pending", next_due, None
            continue
        due_at = review_at or updated_at + timedelta(days=7)
        if review is None:
            session.add(KnowledgeReview(user_id=user_id, document_id=doc.id, status="pending", due_at=due_at))
            review_count += 1
        elif review.status in {"dismissed", "resolved"} and updated_at > _utc(review.updated_at):
            review.status, review.due_at, review.snoozed_until = "pending", due_at, None
            review_count += 1
        elif review.status == "pending":
            review.due_at = due_at
        elif review.status == "snoozed" and review.snoozed_until and review.snoozed_until <= current:
            review.status, review.snoozed_until, review.due_at = "pending", None, due_at
    session.flush()
    return {"insights_created": created_insights, "reviews_created": review_count}
