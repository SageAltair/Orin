"""Bounded, ownership-scoped project context for model interpretation."""
from __future__ import annotations

import uuid
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from orin_api.models import Activity, Memory, Project, Task, TaskStatus


class ProjectContextService:
    def __init__(self, session: Session, user_id: uuid.UUID):
        self.session, self.user_id = session, user_id

    def for_command(self, command: str) -> dict[str, object] | None:
        normalized = command.casefold()
        words = {word for word in re.findall(r"[a-z0-9]+", normalized) if len(word) > 3}
        projects = self.session.scalars(select(Project).where(Project.owner_id == self.user_id).order_by(Project.updated_at.desc()).limit(50)).all()
        matches = [project for project in projects if project.name.casefold() in normalized]
        project = matches[0] if len(matches) == 1 else None
        personal = self.session.scalars(select(Memory).where(Memory.user_id == self.user_id,
            Memory.project_id.is_(None), Memory.memory_type == "preference", Memory.archived.is_(False))
            .order_by(Memory.updated_at.desc()).limit(20)).all()
        preferences = [memory for memory in personal if not words or words.intersection(
            re.findall(r"[a-z0-9]+", f"{memory.title} {memory.content}".casefold()))][:3]
        if project is None:
            return {"user_preferences": [{"title": item.title, "content": item.content} for item in preferences]} if preferences else None
        tasks = self.session.scalars(select(Task).where(Task.owner_id == self.user_id, Task.project_id == project.id).order_by(Task.updated_at.desc()).limit(15)).all()
        activities = self.session.scalars(select(Activity).where(Activity.user_id == self.user_id, Activity.project_id == project.id).order_by(Activity.created_at.desc()).limit(8)).all()
        memories = self.session.scalars(select(Memory).where(Memory.user_id == self.user_id, Memory.project_id == project.id, Memory.archived.is_(False)).order_by(Memory.updated_at.desc()).limit(20)).all()
        asks_decisions = "decision" in words or "decisions" in words
        relevant = [memory for memory in memories if memory.memory_type in {"decision", "fact", "workflow", "project_context"}
                    and (not words or words.intersection(re.findall(r"[a-z0-9]+", f"{memory.title} {memory.content}".casefold()))
                         or (asks_decisions and memory.memory_type == "decision"))][:5]
        return {
            "project": {"name": project.name, "objective": project.objective, "status": project.status.value},
            "tasks": [{"title": task.title, "status": task.status.value} for task in tasks],
            "blockers": [task.title for task in tasks if task.status == TaskStatus.BLOCKED],
            "recent_activity": [item.summary for item in activities],
            "knowledge": [{"type": item.memory_type, "title": item.title, "content": item.content} for item in relevant],
            "user_preferences": [{"title": item.title, "content": item.content} for item in preferences],
        }
