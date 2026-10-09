"""Bounded, ownership-scoped project context for model interpretation."""
from __future__ import annotations

import re
import uuid

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from orin_api.models import Memory, Project, ProjectStatus, Task, TaskDependency, TaskStatus


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
            preferences = self.session.scalars(
                select(Memory).where(Memory.user_id == self.user_id, Memory.project_id.is_(None),
                                     Memory.memory_type == "preference", Memory.archived.is_(False))
                .order_by(Memory.updated_at.desc()).limit(20)
            ).all()
            relevant_preferences = [memory for memory in preferences if words.intersection(
                re.findall(r"[a-z0-9]+", f"{memory.title} {memory.content}".casefold()))][:3]
            return ({"user_preferences": [{"title": item.title, "content": item.content}
                                            for item in relevant_preferences]}
                    if relevant_preferences else None)
        selected_projects = matches if matches else [
            project for project in projects
            if project.status not in {ProjectStatus.COMPLETED, ProjectStatus.ARCHIVED}
        ][:15]
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
        selected_task_ids = {task.id for task in selected_tasks}
        dependencies = self.session.execute(
            select(TaskDependency.task_id, Task.title, Task.status, TaskDependency.depends_on_task_id)
            .join(Task, Task.id == TaskDependency.depends_on_task_id)
            .where(TaskDependency.task_id.in_(selected_task_ids), Task.owner_id == self.user_id)
        ).all() if selected_task_ids else []
        dependency_names: dict[uuid.UUID, list[dict[str, str]]] = {}
        for task_id, title, status, _ in dependencies:
            dependency_names.setdefault(task_id, []).append({"task": title, "status": status.value})
        personal = self.session.scalars(
            select(Memory).where(Memory.user_id == self.user_id, Memory.archived.is_(False))
            .order_by(Memory.updated_at.desc()).limit(30)
        ).all()
        asks_decisions = bool({"decision", "decisions"} & words)
        planning_request = bool({"plan", "planning", "prioritize", "priority", "organize",
                                 "competing", "workstreams", "schedule"} & words)
        relevant_memories = [memory for memory in personal if
            memory.memory_type in {"decision", "fact", "workflow", "project_context", "commitment", "preference"}
            and (not words or words.intersection(re.findall(
                r"[a-z0-9]+", f"{memory.title} {memory.content}".casefold()))
                 or (asks_decisions and memory.memory_type == "decision")
                 or (memory.project_id in selected_ids and memory.memory_type == "decision")
                 or (planning_request and memory.memory_type == "commitment"))
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
                           "due_at": task.due_at,
                           "depends_on": dependency_names.get(task.id, [])}
                          for task in project_tasks[:12]],
                "blockers": [task.title for task in project_tasks if task.status == TaskStatus.BLOCKED],
            })
        return {
            "snapshot_scope": "Named matching projects, or recent active owned projects for planning/workspace questions; active and urgent tasks are prioritized.",
            "may_be_truncated": (len(projects) == 30 or len(selected_projects) == 15
                                 or len(selected_tasks) == 60 or len(personal) == 30
                                 or any(len([task for task in selected_tasks if task.project_id == project.id]) > 12
                                        for project in selected_projects)),
            "projects": project_data,
            "unassigned_tasks": [{"title": task.title, "status": task.status.value,
                                  "priority": task.priority.value if task.priority else None,
                                  "due_at": task.due_at,
                                  "depends_on": dependency_names.get(task.id, [])}
                                 for task in selected_tasks if task.project_id is None],
            "memories_and_commitments": [{"type": item.memory_type, "title": item.title,
                                         "content": item.content} for item in relevant_memories],
        }
