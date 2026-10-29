"""Bounded, ownership-scoped project context for model interpretation."""
from __future__ import annotations

import re
import uuid

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from orin_api.models import KnowledgeDocument, Memory, Project, ProjectStatus, Task, TaskDependency, TaskStatus
from orin_api.memory_context import MemoryContextService, memory_provenance


class ProjectContextService:
    def __init__(self, session: Session, user_id: uuid.UUID):
        self.session, self.user_id = session, user_id

    def for_command(self, command: str, *, active_objective: str | None = None) -> dict[str, object] | None:
        """Return a bounded workspace snapshot, even for cross-project planning."""
        normalized = f"{active_objective or ''} {command}".casefold()
        words = {word for word in re.findall(r"[^\W_]+", normalized, re.UNICODE) if len(word) > 3}
        notes_query = select(KnowledgeDocument).where(KnowledgeDocument.user_id == self.user_id,
            KnowledgeDocument.archived.is_(False), KnowledgeDocument.exclude_from_ai.is_(False),
            KnowledgeDocument.document_type != "journal")
        relevant_notes = self.session.scalars(notes_query.where(or_(*[
            KnowledgeDocument.title.ilike(f"%{word}%") | KnowledgeDocument.content.ilike(f"%{word}%")
            for word in words])).order_by(KnowledgeDocument.updated_at.desc()).limit(6)).all() if words else []
        note_context = [{"document_id": str(note.id), "title": note.title, "excerpt": note.content[:1800]}
                        for note in relevant_notes]
        projects = self.session.scalars(
            select(Project).where(Project.owner_id == self.user_id)
            .order_by(Project.updated_at.desc()).limit(30)
        ).all()
        matches = [project for project in projects if project.name.casefold() in normalized]
        workspace_terms = {
            "project", "projects", "task", "tasks", "workspace", "plan", "planning",
            "prioritize", "prioritise", "priorities", "organize", "organise", "workstream",
            "workstreams", "competing", "commitment", "commitments", "blocker", "blockers",
            "progress", "status", "schedule", "schedules", "deadline", "deadlines",
            "income", "rent", "urgent", "job", "jobs", "work", "overwhelmed", "overwhelm",
            "balance", "week", "weekly", "month", "monthly", "focus",
        }
        workspace_phrases = (
            "next action", "due date", "what should i do first", "decide what to do first",
            "too many things", "too much on my plate", "where should i start",
        )
        is_workspace_request = bool(workspace_terms.intersection(words)) or any(
            phrase in normalized for phrase in workspace_phrases
        )
        if not matches and not is_workspace_request:
            relevant = MemoryContextService(self.session, self.user_id).relevant(normalized, limit=3)
            return ({"writing_sources": note_context, "relevant_memories": [
                {"id": str(item.memory.id), "type": item.memory.memory_type, "title": item.memory.title,
                 "content": item.memory.content, "provenance": memory_provenance(item.memory),
                 "confidence": item.memory.confidence, "relevance_reasons": list(item.reasons)}
                for item in relevant]}
                    if relevant or note_context else None)
        inventory_request = any(phrase in command.casefold() for phrase in (
            "all my projects", "all projects", "my existing projects", "review my workspace",
            "review all my tasks", "what tasks do i have", "list my projects", "list my tasks",
        ))
        active_projects = [project for project in projects
            if project.status not in {ProjectStatus.COMPLETED, ProjectStatus.ARCHIVED}]
        if matches:
            selected_projects = matches
        elif inventory_request:
            selected_projects = active_projects[:15]
        else:
            selected_projects = [project for project in active_projects
                if {w for w in re.findall(r"[a-z0-9]+", project.name.casefold()) if len(w) > 3}.intersection(words)][:15]
        selected_ids = {project.id for project in selected_projects}

        task_query = select(Task).where(Task.owner_id == self.user_id)
        if selected_ids:
            task_query = task_query.where(or_(Task.project_id.in_(selected_ids), Task.project_id.is_(None)))
        else:
            task_query = task_query.where(Task.project_id.is_(None))
        selected_tasks = self.session.scalars(
            task_query.order_by(
                case((Task.status == TaskStatus.BLOCKED, 0), (Task.status == TaskStatus.IN_PROGRESS, 1),
                     (Task.status == TaskStatus.TODO, 2), else_=3),
                case((Task.priority == "urgent", 0), (Task.priority == "high", 1),
                     (Task.priority == "normal", 2), else_=3),
                Task.due_at.asc().nulls_last(), Task.updated_at.desc(),
            ).limit(60)
        ).all()
        if not matches and not inventory_request:
            selected_tasks = [task for task in selected_tasks if task.project_id in selected_ids or
                words.intersection(re.findall(r"[a-z0-9]+", task.title.casefold() + " " + (task.description or "").casefold()))]
        selected_task_ids = {task.id for task in selected_tasks}
        dependencies = self.session.execute(
            select(TaskDependency.task_id, Task.title, Task.status, TaskDependency.depends_on_task_id)
            .join(Task, Task.id == TaskDependency.depends_on_task_id)
            .where(TaskDependency.task_id.in_(selected_task_ids), Task.owner_id == self.user_id)
        ).all() if selected_task_ids else []
        dependency_names: dict[uuid.UUID, list[dict[str, str]]] = {}
        for task_id, title, status, _ in dependencies:
            dependency_names.setdefault(task_id, []).append({"task": title, "status": status.value})
        ranked_memories = MemoryContextService(self.session, self.user_id).relevant(
            normalized, project_ids=selected_ids, limit=10)
        relevant_memories = [item.memory for item in ranked_memories
            if item.memory.project_id is None or item.memory.project_id in selected_ids]
        if not selected_projects and not selected_tasks and not relevant_memories and not note_context:
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
                           "due_at": task.due_at,
                           "depends_on": dependency_names.get(task.id, [])}
                          for task in project_tasks[:12]],
                "blockers": [task.title for task in project_tasks if task.status == TaskStatus.BLOCKED],
            })
        return {
            "writing_sources": note_context,
            "snapshot_scope": "Named matching projects, or recent active owned projects for planning/workspace questions; active and urgent tasks are prioritized.",
            "may_be_truncated": (len(projects) == 30 or len(selected_projects) == 15
                                 or len(selected_tasks) == 60
                                 or any(len([task for task in selected_tasks if task.project_id == project.id]) > 12
                                        for project in selected_projects)),
            "projects": project_data,
            "unassigned_tasks": [{"title": task.title, "status": task.status.value,
                                  "priority": task.priority.value if task.priority else None,
                                  "due_at": task.due_at,
                                  "depends_on": dependency_names.get(task.id, [])}
                                 for task in selected_tasks if task.project_id is None],
            "memories_and_commitments": [{"id": str(item.id), "type": item.memory_type,
                                         "title": item.title, "content": item.content,
                                         "provenance": memory_provenance(item),
                                         "confidence": item.confidence,
                                         "relevance_reasons": list(next((ranked.reasons for ranked in ranked_memories if ranked.memory.id == item.id), ())),
                                         "metadata": item.metadata_json} for item in relevant_memories],
        }
