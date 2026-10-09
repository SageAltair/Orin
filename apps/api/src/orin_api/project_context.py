"""Bounded, ownership-scoped project context for model interpretation."""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from orin_api.models import Memory, Project, Task, TaskStatus


class ProjectContextService:
    def __init__(self, session: Session, user_id: uuid.UUID):
        self.session, self.user_id = session, user_id

    def for_command(self, command: str) -> dict[str, object] | None:
        """Return a bounded workspace snapshot, even for cross-project planning."""
        normalized = command.casefold()
        words = {word for word in re.findall(r"[a-z0-9]+", normalized) if len(word) > 3}
        projects = self.session.scalars(
            select(Project).where(Project.owner_id == self.user_id)
            .order_by(Project.updated_at.desc()).limit(30)
        ).all()
        matches = [project for project in projects if project.name.casefold() in normalized]
        selected_projects = matches if matches else projects[:15]
        selected_ids = {project.id for project in selected_projects}

        tasks = self.session.scalars(
            select(Task).where(Task.owner_id == self.user_id)
            .order_by(Task.updated_at.desc()).limit(50)
        ).all()
        selected_tasks = [task for task in tasks if task.project_id in selected_ids or task.project_id is None][:30]
        personal = self.session.scalars(
            select(Memory).where(Memory.user_id == self.user_id, Memory.archived.is_(False))
            .order_by(Memory.updated_at.desc()).limit(30)
        ).all()
        relevant_memories = [memory for memory in personal if
            memory.memory_type in {"decision", "fact", "workflow", "project_context", "commitment", "preference"}
            and (not words or words.intersection(re.findall(
                r"[a-z0-9]+", f"{memory.title} {memory.content}".casefold()))
                 or memory.memory_type in {"commitment", "decision"})
            and (memory.project_id is None or memory.project_id in selected_ids)][:10]
        if not selected_projects and not selected_tasks and not relevant_memories:
            return None

        project_data = []
        for project in selected_projects:
            project_tasks = [task for task in selected_tasks if task.project_id == project.id]
            project_data.append({
                "name": project.name,
                "description": project.description,
                "objective": project.objective,
                "status": project.status.value,
                "tasks": [{"title": task.title, "status": task.status.value,
                           "priority": task.priority.value if task.priority else None,
                           "due_at": task.due_at}
                          for task in project_tasks[:12]],
                "blockers": [task.title for task in project_tasks if task.status == TaskStatus.BLOCKED],
            })
        return {
            "projects": project_data,
            "unassigned_tasks": [{"title": task.title, "status": task.status.value,
                                  "priority": task.priority.value if task.priority else None,
                                  "due_at": task.due_at}
                                 for task in selected_tasks if task.project_id is None],
            "memories_and_commitments": [{"type": item.memory_type, "title": item.title,
                                         "content": item.content} for item in relevant_memories],
        }
