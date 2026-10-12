"""Deterministic, evidence-linked knowledge patterns and review eligibility."""
from __future__ import annotations

import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from orin_api.models import KnowledgeDocument, KnowledgeInsight, KnowledgeReview, Task, TaskReturnPoint, TaskStatus

STOP_WORDS = frozenset("about after again also because before being between could did does doing down each from have here into just more most only other should some such than that their them then there these they this those through under until very what when where which while with would your".split())
TOKEN = re.compile(r"[^\W\d_][\w'-]{3,}", re.UNICODE)


def invalidate_document_insights(session: Session, user_id: uuid.UUID, document_id: uuid.UUID) -> None:
    """Remove derived evidence as soon as a source changes or becomes private."""
    for row in session.scalars(select(KnowledgeInsight).where(KnowledgeInsight.user_id == user_id)).all():
        if any(str(item.get("document_id")) == str(document_id) for item in row.evidence if isinstance(item, dict)):
            session.delete(row)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _upsert_insight(session: Session, *, user_id: uuid.UUID, insight_type: str, fingerprint: str,
                    title: str, explanation: str, evidence: list[dict[str, object]], frequency: int,
                    confidence: float, limitations: str, suggested_next_step: str,
                    window_start: datetime | None, window_end: datetime | None, now: datetime) -> int:
    insight = session.scalar(select(KnowledgeInsight).where(
        KnowledgeInsight.user_id == user_id,
        KnowledgeInsight.insight_type == insight_type,
        KnowledgeInsight.fingerprint == fingerprint,
    ))
    if insight is not None and insight.status in {"dismissed", "resolved"}:
        return 0
    if insight is None:
        session.add(KnowledgeInsight(user_id=user_id, insight_type=insight_type, fingerprint=fingerprint,
            title=title, explanation=explanation, evidence=evidence, frequency=frequency, confidence=confidence,
            limitations=limitations, suggested_next_step=suggested_next_step, window_start=window_start,
            window_end=window_end, status="active", evaluated_at=now))
        return 1
    insight.title, insight.explanation, insight.evidence = title, explanation, evidence
    insight.frequency, insight.confidence = frequency, confidence
    insight.limitations, insight.suggested_next_step = limitations, suggested_next_step
    insight.window_start, insight.window_end, insight.evaluated_at = window_start, window_end, now
    if insight.status == "snoozed" and insight.snoozed_until and _utc(insight.snoozed_until) <= _utc(now):
        insight.status, insight.snoozed_until = "active", None
    return 0


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

    # A source can disappear, change type or lose eligibility between evaluations.
    eligible_ids = {str(doc.id) for doc in docs}
    for insight in session.scalars(select(KnowledgeInsight).where(KnowledgeInsight.user_id == user_id)).all():
        document_evidence = [item for item in insight.evidence if isinstance(item, dict) and item.get("document_id")]
        invalid = any(str(item["document_id"]) not in eligible_ids for item in document_evidence)
        if insight.fingerprint.startswith("topic:"):
            invalid = invalid or len(topic_documents.get(insight.fingerprint[6:], [])) < 3
        if insight.fingerprint.startswith("trend:"):
            sources = topic_documents.get(insight.fingerprint[6:], [])
            recent = [doc for doc in sources if _utc(doc.updated_at) >= current - timedelta(days=14)]
            prior = [doc for doc in sources if current - timedelta(days=44) <= _utc(doc.updated_at) < current - timedelta(days=14)]
            invalid = invalid or len(recent) < 2 or len(recent) <= len(prior)
        if insight.fingerprint == "dormant:ideas":
            invalid = invalid or not any(doc.document_type == "idea" and doc.status not in {"completed", "parked", "abandoned"} and _utc(doc.updated_at) <= current - timedelta(days=30) for doc in docs)
        if insight.fingerprint == "unfinished:drafts:21d":
            invalid = invalid or sum(doc.document_type == "draft" and doc.status in {"developing", "ready_to_resume"} and _utc(doc.updated_at) <= current - timedelta(days=21) for doc in docs) < 2
        if invalid:
            session.delete(insight)
    session.flush()
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

    # A recent rise is shown only when both windows contain evidence.
    recent_cutoff, prior_cutoff = current - timedelta(days=14), current - timedelta(days=44)
    for term, sources in topic_documents.items():
        recent = [doc for doc in sources if _utc(doc.updated_at) >= recent_cutoff]
        prior = [doc for doc in sources if prior_cutoff <= _utc(doc.updated_at) < recent_cutoff]
        if len(recent) < 2 or len(recent) <= len(prior):
            continue
        evidence = [{"document_id": str(doc.id), "title": doc.title, "updated_at": doc.updated_at.isoformat()}
                    for doc in sorted(recent, key=lambda item: _utc(item.updated_at), reverse=True)[:10]]
        created_insights += _upsert_insight(session, user_id=user_id, insight_type="emerging_topic",
            fingerprint=f"trend:{term}"[:160], title=f"More recent writing mentions: {term}",
            explanation=f"{len(recent)} distinct matching documents were updated in the last 14 days, compared with {len(prior)} in the preceding 30 days. This reflects document activity, not personal importance.",
            evidence=evidence, frequency=len(recent), confidence=0.6,
            limitations="Activity windows are sensitive to edits and do not establish a change in interest.",
            suggested_next_step="Review the linked records and decide whether this topic needs a project or follow-up.",
            window_start=recent_cutoff, window_end=current, now=current)

    dormant_ideas = [doc for doc in docs if doc.document_type == "idea" and doc.status not in {"completed", "parked", "abandoned"}
                     and _utc(doc.updated_at) <= current - timedelta(days=30)]
    if dormant_ideas:
        evidence = [{"document_id": str(doc.id), "title": doc.title, "updated_at": doc.updated_at.isoformat()}
                    for doc in dormant_ideas[:10]]
        created_insights += _upsert_insight(session, user_id=user_id, insight_type="dormant_ideas",
            fingerprint="dormant:ideas", title=f"{len(dormant_ideas)} ideas have been quiet for 30 days",
            explanation="These ideas remain open and have not been edited for at least 30 days.", evidence=evidence,
            frequency=len(dormant_ideas), confidence=0.8,
            limitations="Age alone does not indicate that an idea remains relevant.",
            suggested_next_step="Revisit, connect, park, or abandon each idea if useful.",
            window_start=min(_utc(doc.updated_at) for doc in dormant_ideas), window_end=current, now=current)

    dormant_drafts = [doc for doc in docs if doc.document_type == "draft" and doc.status in {"developing", "ready_to_resume"}
                      and _utc(doc.updated_at) <= current - timedelta(days=21)]
    if len(dormant_drafts) >= 2:
        evidence = [{"document_id": str(doc.id), "title": doc.title, "updated_at": doc.updated_at.isoformat()}
                    for doc in dormant_drafts[:10]]
        created_insights += _upsert_insight(session, user_id=user_id, insight_type="unfinished_drafts",
            fingerprint="unfinished:drafts:21d", title=f"{len(dormant_drafts)} drafts have been quiet for 21 days",
            explanation="These documents are still developing or ready to resume and have not been edited for at least 21 days.",
            evidence=evidence, frequency=len(dormant_drafts), confidence=0.85,
            limitations="Quiet periods can be intentional, and this does not mean the drafts need a deadline.",
            suggested_next_step="Resume, park, or abandon each draft based on your current priorities.",
            window_start=min(_utc(doc.updated_at) for doc in dormant_drafts), window_end=current, now=current)

    # Repeated task return-point blockers are observed from existing task records.
    blockers: dict[str, list[tuple[Task, TaskReturnPoint]]] = defaultdict(list)
    rows = session.execute(select(Task, TaskReturnPoint).join(TaskReturnPoint, TaskReturnPoint.task_id == Task.id).where(
        Task.owner_id == user_id, TaskReturnPoint.user_id == user_id,
        Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
    ).order_by(TaskReturnPoint.created_at.desc()).limit(500)).all()
    for task, point in rows:
        if point.blocker and len(point.blocker.strip()) >= 8:
            key = re.sub(r"\s+", " ", point.blocker.casefold()).strip()
            blockers[key].append((task, point))
    for blocker, records in blockers.items():
        unique_tasks = {task.id: task for task, _ in records}
        if len(records) < 2 or len(unique_tasks) < 2:
            continue
        evidence = [{"task_id": str(task.id), "title": task.title, "record_type": "task"}
                    for task in list(unique_tasks.values())[:10]]
        fingerprint = f"blocker:{blocker}"[:160]
        created_insights += _upsert_insight(session, user_id=user_id, insight_type="repeated_blocker",
            fingerprint=fingerprint, title="A similar blocker appears on multiple open tasks",
            explanation=f"A similar blocker was recorded {len(records)} times across {len(unique_tasks)} open tasks. This may describe a shared dependency, but the notes could refer to different situations.",
            evidence=evidence, frequency=len(records), confidence=0.7,
            limitations="Blockers are grouped by matching text and may not share the same cause.",
            suggested_next_step="Review the linked tasks and decide whether to record a next action or change their status.",
            window_start=min(_utc(point.created_at) for _, point in records), window_end=current, now=current)

    review_count = 0
    by_document = {doc.id: doc for doc in session.scalars(select(KnowledgeDocument).where(KnowledgeDocument.user_id == user_id)).all()}
    for doc in by_document.values():
        review = session.scalar(select(KnowledgeReview).where(KnowledgeReview.document_id == doc.id, KnowledgeReview.user_id == user_id))
        eligible_status = (doc.status not in {"completed", "parked", "abandoned"} and not doc.archived
                           and not doc.exclude_from_ai and doc.document_type != "journal")
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
        elif review.status == "snoozed" and review.snoozed_until and _utc(review.snoozed_until) <= _utc(current):
            review.status, review.snoozed_until, review.due_at = "pending", None, due_at
    session.flush()
    return {"insights_created": created_insights, "reviews_created": review_count}
