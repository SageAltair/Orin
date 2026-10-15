"""Bounded, explainable retrieval for personal intelligence memory."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from orin_api.models import Memory


MEMORY_TYPES = {
    "identity", "working_style", "project", "commitment", "knowledge", "interaction", "pattern",
    # Existing records remain valid and are included in retrieval.
    "preference", "decision", "fact", "workflow", "project_context",
}
_TYPE_TERMS = {
    "identity": {"goal", "goals", "role", "roles", "value", "values", "identity"},
    "working_style": {"work", "focus", "schedule", "routine", "energy", "preference", "prefer"},
    "project": {"project", "projects", "objective", "blocker", "decision", "progress"},
    "commitment": {"commitment", "commitments", "promise", "deadline", "follow", "appointment"},
    "knowledge": {"know", "knowledge", "note", "notes", "idea", "ideas", "document"},
    "interaction": {"suggestion", "suggestions", "accepted", "dismissed", "corrected", "feedback"},
    "pattern": {"pattern", "patterns", "often", "usually", "repeated", "reschedule", "recurring"},
}
_LEGACY_CATEGORY = {"preference": "working_style", "decision": "project", "fact": "knowledge",
                    "workflow": "working_style", "project_context": "project"}


def memory_provenance(memory: Memory) -> str:
    value = memory.metadata_json.get("provenance") if isinstance(memory.metadata_json, dict) else None
    if value in {"explicit", "inferred", "verified"}:
        return str(value)
    return "inferred" if memory.source == "inferred" else "explicit"


@dataclass(frozen=True)
class RankedMemory:
    memory: Memory
    score: float
    reasons: tuple[str, ...]


class MemoryContextService:
    def __init__(self, session: Session, user_id: uuid.UUID):
        self.session, self.user_id = session, user_id

    def relevant(self, query: str, *, project_ids: set[uuid.UUID] | None = None,
                 limit: int = 10) -> list[RankedMemory]:
        words = {word for word in re.findall(r"[^\W_]+", query.casefold(), re.UNICODE) if len(word) > 2}
        rows = self.session.scalars(select(Memory).where(
            Memory.user_id == self.user_id, Memory.archived.is_(False),
        ).order_by(Memory.updated_at.desc()).limit(200)).all()
        ranked: list[RankedMemory] = []
        for memory in rows:
            memory_words = set(re.findall(r"[^\W_]+", f"{memory.title} {memory.content}".casefold(), re.UNICODE))
            overlap = words.intersection(memory_words)
            category = _LEGACY_CATEGORY.get(memory.memory_type, memory.memory_type)
            reasons: list[str] = []
            score = min(len(overlap), 6) * 2.0
            if overlap:
                reasons.append("matches request terms")
            if words.intersection(_TYPE_TERMS.get(category, set())):
                score += 2.5; reasons.append(f"relevant {category.replace('_', ' ')} context")
            if project_ids and memory.project_id in project_ids:
                score += 4.0; reasons.append("belongs to the active project")
            if memory.memory_type == "commitment" and words.intersection({"plan", "priority", "week", "schedule", "commitment"}):
                score += 3.0; reasons.append("active commitment")
            provenance = memory_provenance(memory)
            confidence = memory.confidence if memory.confidence is not None else (1.0 if provenance != "inferred" else 0.5)
            score *= max(0.25, confidence)
            if provenance == "inferred":
                reasons.append("inferred pattern")
            if score > 0:
                ranked.append(RankedMemory(memory, round(score, 3), tuple(dict.fromkeys(reasons))))
        ranked.sort(key=lambda item: (item.score, item.memory.updated_at), reverse=True)
        return ranked[:max(1, min(limit, 20))]
