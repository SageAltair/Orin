from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from orin_api.database import Base


class Theme(str, enum.Enum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class Density(str, enum.Enum):
    COMFORTABLE = "comfortable"
    COMPACT = "compact"


class ProjectStatus(str, enum.Enum):
    PLANNING = "planning"
    ACTIVE = "active"
    BLOCKED = "blocked"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ProjectRole(str, enum.Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class TaskStatus(str, enum.Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class FocusState(str, enum.Enum):
    INBOX = "inbox"
    LATER = "later"
    TODAY = "today"
    ACTIVE = "active"
    RELEASED = "released"


class EnergyLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DriftTrigger(str, enum.Enum):
    APP = "app"
    THOUGHT = "thought"
    EMOTION = "emotion"
    PERSON = "person"
    TIRED = "tired"
    OTHER = "other"


class CommandStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ExecutionStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    EXECUTED = "executed"


class DeviceStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    REVOKED = "revoked"
    OFFLINE = "offline"


class WorkerJobStatus(str, enum.Enum):
    PENDING_APPROVAL = "pending_approval"
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ActivityType(str, enum.Enum):
    PROJECT_CREATED = "project_created"
    PROJECT_UPDATED = "project_updated"
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASKS_CREATED_BATCH = "tasks_created_batch"
    MEMORY_CHANGED = "memory_changed"
    FOCUS_UPDATED = "focus_updated"
    COMMAND_RECEIVED = "command_received"
    INTENT_INTERPRETED = "intent_interpreted"
    PLAN_CREATED = "plan_created"
    COMMAND_COMPLETED = "command_completed"
    COMMAND_FAILED = "command_failed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_DECIDED = "approval_decided"
    WORKER_JOB_QUEUED = "worker_job_queued"
    WORKER_JOB_STARTED = "worker_job_started"
    WORKER_JOB_PROGRESS = "worker_job_progress"
    WORKER_JOB_COMPLETED = "worker_job_completed"
    WORKER_JOB_FAILED = "worker_job_failed"
    WORKER_JOB_CANCELLED = "worker_job_cancelled"
    WORKER_JOB_TIMED_OUT = "worker_job_timed_out"
    WORKER_CONNECTED = "worker_connected"
    WORKER_DISCONNECTED = "worker_disconnected"
    POLICY_DECISION = "policy_decision"
    INTEGRATION_OPERATION = "integration_operation"


def enum_column(enum_class: type[enum.Enum], name: str) -> Enum:
    return Enum(
        enum_class,
        name=name,
        values_callable=lambda members: [member.value for member in members],
        native_enum=True,
        validate_strings=True,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
        server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc)
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default=func.now())


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint("(email IS NULL) = (password_hash IS NULL)", name="ck_user_credentials_together"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)

    preferences: Mapped[UserPreferences] = relationship(back_populates="user", cascade="all, delete-orphan", uselist=False)
    capabilities: Mapped[list[UserCapability]] = relationship(back_populates="user", cascade="all, delete-orphan")
    projects: Mapped[list[Project]] = relationship(back_populates="owner")
    tasks: Mapped[list[Task]] = relationship(back_populates="owner", foreign_keys="Task.owner_id")
    auth_sessions: Mapped[list[AuthSession]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserPreferences(TimestampMixin, Base):
    __tablename__ = "user_preferences"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_preferences_user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    density: Mapped[Density] = mapped_column(enum_column(Density, "density"), nullable=False, default=Density.COMFORTABLE, server_default=Density.COMFORTABLE.value)
    theme: Mapped[Theme] = mapped_column(enum_column(Theme, "theme"), nullable=False, default=Theme.LIGHT, server_default=Theme.LIGHT.value)
    locale: Mapped[str] = mapped_column(String(20), nullable=False, default="en", server_default="en")
    autonomy_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="balanced", server_default="balanced")
    custom_autonomy: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")

    user: Mapped[User] = relationship(back_populates="preferences")


class Capability(Base):
    __tablename__ = "capabilities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(240), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    user_assignments: Mapped[list[UserCapability]] = relationship(back_populates="capability", cascade="all, delete-orphan")


class UserCapability(TimestampMixin, Base):
    __tablename__ = "user_capabilities"
    __table_args__ = (
        UniqueConstraint("user_id", "capability_id", name="uq_user_capability"),
        CheckConstraint("pinned = false OR visible = true", name="ck_user_capability_pinned_visible"),
        CheckConstraint("visible = false OR granted = true", name="ck_user_capability_visible_granted"),
        Index("ix_user_capabilities_user_visible", "user_id", "visible"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    capability_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("capabilities.id", ondelete="CASCADE"), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    user: Mapped[User] = relationship(back_populates="capabilities")
    capability: Mapped[Capability] = relationship(back_populates="user_assignments")


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_owner_status_updated", "owner_id", "status", "updated_at"),
        CheckConstraint("length(trim(name)) > 0", name="ck_projects_name_nonempty"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    objective: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(enum_column(ProjectStatus, "project_status"), nullable=False, default=ProjectStatus.ACTIVE, server_default=ProjectStatus.ACTIVE.value)

    owner: Mapped[User] = relationship(back_populates="projects")
    members: Mapped[list[ProjectMember]] = relationship(back_populates="project", cascade="all, delete-orphan")
    tasks: Mapped[list[Task]] = relationship(back_populates="project")


class ProjectMember(TimestampMixin, Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[ProjectRole] = mapped_column(enum_column(ProjectRole, "project_role"), nullable=False, default=ProjectRole.VIEWER, server_default=ProjectRole.VIEWER.value)

    project: Mapped[Project] = relationship(back_populates="members")


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_owner_status_due", "owner_id", "status", "due_at"),
        Index("ix_tasks_owner_decay_review", "owner_id", "decay_review_at"),
        Index("ix_tasks_project_status", "project_id", "status"),
        Index("ix_tasks_assignee_status", "assignee_id", "status"),
        CheckConstraint("length(trim(title)) > 0", name="ck_tasks_title_nonempty"),
        CheckConstraint("estimated_minutes IS NULL OR estimated_minutes > 0", name="ck_tasks_estimated_minutes_positive"),
        CheckConstraint("skip_count_today BETWEEN 0 AND 2", name="ck_tasks_skip_count_today_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(enum_column(TaskStatus, "task_status"), nullable=False, default=TaskStatus.TODO, server_default=TaskStatus.TODO.value)
    priority: Mapped[TaskPriority] = mapped_column(enum_column(TaskPriority, "task_priority"), nullable=False, default=TaskPriority.NORMAL, server_default=TaskPriority.NORMAL.value)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    focus_state: Mapped[FocusState | None] = mapped_column(enum_column(FocusState, "focus_state"), nullable=True, default=FocusState.INBOX)
    first_step: Mapped[str | None] = mapped_column(Text)
    why: Mapped[str | None] = mapped_column(String(500))
    energy_level: Mapped[EnergyLevel | None] = mapped_column(enum_column(EnergyLevel, "task_energy_level"), nullable=True)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    is_anchor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    trigger: Mapped[str | None] = mapped_column(String(240))
    last_touched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decay_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    skip_count_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    skip_day_key: Mapped[str | None] = mapped_column(String(10))
    today_day_key: Mapped[str | None] = mapped_column(String(10))
    today_position: Mapped[int | None] = mapped_column(Integer)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner: Mapped[User] = relationship(back_populates="tasks", foreign_keys=[owner_id])
    project: Mapped[Project | None] = relationship(back_populates="tasks")
    dependencies: Mapped[list[TaskDependency]] = relationship(foreign_keys="TaskDependency.task_id", back_populates="task", cascade="all, delete-orphan")


class TaskDependency(CreatedAtMixin, Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependency"),
        CheckConstraint("task_id <> depends_on_task_id", name="ck_task_dependency_not_self"),
        Index("ix_task_dependencies_depends_on", "depends_on_task_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    depends_on_task_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    task: Mapped[Task] = relationship(foreign_keys=[task_id], back_populates="dependencies")


class Conversation(TimestampMixin, Base):
    """Persistent work session that owns a sequence of user and assistant turns."""
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_user_updated", "user_id", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(240), nullable=False, default="New work session")
    objective: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    summary_through_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pending_question: Mapped[dict[str, object] | None] = mapped_column(JSON)


class Command(TimestampMixin, Base):
    __tablename__ = "commands"
    __table_args__ = (Index("ix_commands_user_created", "user_id", "created_at"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_command_user_idempotency"))

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"))
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CommandStatus] = mapped_column(enum_column(CommandStatus, "command_status"), nullable=False, default=CommandStatus.SUBMITTED, server_default=CommandStatus.SUBMITTED.value)
    idempotency_key: Mapped[str | None] = mapped_column(String(160))
    response_intent: Mapped[str | None] = mapped_column(String(40))
    response_json: Mapped[dict[str, object] | list[dict[str, object]] | None] = mapped_column(JSON)
    response_message: Mapped[str | None] = mapped_column(Text)
    response_execution_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    attachment_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")


class FileAttachment(CreatedAtMixin, Base):
    __tablename__ = "file_attachments"
    __table_args__ = (Index("ix_file_attachments_owner_conversation", "owner_id", "conversation_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"))
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"))
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text)


class RequestRateWindow(Base):
    __tablename__ = "request_rate_windows"
    __table_args__ = (
        UniqueConstraint("user_id", "route", "window_start", name="uq_request_rate_user_route_window"),
        Index("ix_request_rate_window_start", "window_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    route: Mapped[str] = mapped_column(String(60), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_count: Mapped[int] = mapped_column(nullable=False)


class Execution(TimestampMixin, Base):
    __tablename__ = "executions"
    __table_args__ = (Index("ix_executions_status_created", "status", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    command_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("commands.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[ExecutionStatus] = mapped_column(enum_column(ExecutionStatus, "execution_status"), nullable=False, default=ExecutionStatus.QUEUED, server_default=ExecutionStatus.QUEUED.value)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)


class Approval(TimestampMixin, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint(
            "(command_id IS NOT NULL AND execution_id IS NULL) OR (command_id IS NULL AND execution_id IS NOT NULL)",
            name="ck_approval_exactly_one_subject",
        ),
        Index("ix_approvals_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    command_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("commands.id", ondelete="CASCADE"))
    execution_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"))
    requested_by_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[ApprovalStatus] = mapped_column(enum_column(ApprovalStatus, "approval_status"), nullable=False, default=ApprovalStatus.PENDING, server_default=ApprovalStatus.PENDING.value)
    decision_note: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    action_name: Mapped[str | None] = mapped_column(String(80))
    action_payload: Mapped[dict[str, object] | None] = mapped_column(JSON)
    risk_level: Mapped[str | None] = mapped_column(String(20))
    permission: Mapped[str | None] = mapped_column(String(80))
    reversible: Mapped[bool | None] = mapped_column(Boolean)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExecutionAudit(CreatedAtMixin, Base):
    __tablename__ = "execution_audit"
    __table_args__ = (
        Index("ix_execution_audit_user_created", "user_id", "created_at"),
        Index("ix_execution_audit_command", "command_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    command_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("commands.id", ondelete="CASCADE"), nullable=False)
    action_name: Mapped[str] = mapped_column(String(80), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    permission: Mapped[str] = mapped_column(String(80), nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    execution_status: Mapped[str] = mapped_column(String(30), nullable=False)
    result_status: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(36))
    approval_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("approvals.id", ondelete="SET NULL"))


class Activity(CreatedAtMixin, Base):
    __tablename__ = "activity"
    __table_args__ = (
        Index("ix_activity_user_created", "user_id", "created_at"),
        Index("ix_activity_project_created", "project_id", "created_at"),
        Index("ix_activity_task_created", "task_id", "created_at"),
        Index("ix_activity_execution_created", "execution_id", "created_at"),
        Index("ix_activity_user_type_created", "user_id", "activity_type", "created_at"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_activity_user_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    command_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("commands.id", ondelete="SET NULL"))
    execution_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("executions.id", ondelete="SET NULL"))
    approval_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("approvals.id", ondelete="SET NULL"))
    worker_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("worker_jobs.id", ondelete="SET NULL"))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"))
    activity_type: Mapped[ActivityType] = mapped_column(enum_column(ActivityType, "activity_type"), nullable=False)
    summary: Mapped[str] = mapped_column(String(240), nullable=False)
    intent: Mapped[str | None] = mapped_column(String(40))
    result_status: Mapped[str] = mapped_column(String(20), nullable=False, default="succeeded", server_default="succeeded")
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info", server_default="info")
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="api", server_default="api")
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(160))
    metadata_json: Mapped[dict[str, object]] = mapped_column("metadata", JSON, nullable=False, default=dict, server_default="{}")


class AuthSession(CreatedAtMixin, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (Index("ix_auth_sessions_user_active", "user_id", "revoked_at", "expires_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="auth_sessions")
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(back_populates="auth_session", cascade="all, delete-orphan", foreign_keys="RefreshToken.session_id")


class RefreshToken(CreatedAtMixin, Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        CheckConstraint("length(token_hash) = 64", name="ck_refresh_token_hash_sha256"),
        Index("ix_refresh_tokens_session_expiry", "session_id", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth_sessions.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("refresh_tokens.id", ondelete="SET NULL"), unique=True)

    auth_session: Mapped[AuthSession] = relationship(back_populates="refresh_tokens", foreign_keys=[session_id])


class WorkerDevice(TimestampMixin, Base):
    __tablename__ = "worker_devices"
    __table_args__ = (Index("ix_worker_devices_owner_status", "owner_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    platform: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    credential_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[DeviceStatus] = mapped_column(enum_column(DeviceStatus, "device_status"), nullable=False, default=DeviceStatus.PENDING, server_default="pending")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkerJob(TimestampMixin, Base):
    __tablename__ = "worker_jobs"
    __table_args__ = (
        UniqueConstraint("nonce", name="uq_worker_job_nonce"),
        CheckConstraint("requested_target IN ('local', 'cloud', 'auto')", name="ck_worker_job_requested_target"),
        CheckConstraint("selected_target IS NULL OR selected_target IN ('local', 'cloud')", name="ck_worker_job_selected_target"),
        Index("ix_worker_jobs_device_status_created", "device_id", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("worker_devices.id", ondelete="CASCADE"), nullable=False)
    approval_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("approvals.id", ondelete="CASCADE"), nullable=False, unique=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    parameters: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[WorkerJobStatus] = mapped_column(enum_column(WorkerJobStatus, "worker_job_status"), nullable=False, default=WorkerJobStatus.PENDING_APPROVAL, server_default="pending_approval")
    nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    progress: Mapped[str | None] = mapped_column(String(240))
    result: Mapped[dict[str, object] | None] = mapped_column(JSON)
    failure: Mapped[str | None] = mapped_column(String(240))
    requested_target: Mapped[str] = mapped_column(String(12), nullable=False, default="auto", server_default="auto")
    selected_target: Mapped[str | None] = mapped_column(String(12))


class Memory(TimestampMixin, Base):
    __tablename__ = "memories"
    __table_args__ = (Index("ix_memories_user_project_type", "user_id", "project_id", "memory_type", "archived"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    memory_type: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(240), nullable=False)
    confidence: Mapped[float | None] = mapped_column()
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    metadata_json: Mapped[dict[str, object]] = mapped_column("metadata", JSON, nullable=False, default=dict, server_default="{}")


class EnvironmentPreference(TimestampMixin, Base):
    __tablename__ = "environment_preferences"
    __table_args__ = (UniqueConstraint("user_id", "surface", "item", name="uq_environment_preference_item"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    surface: Mapped[str] = mapped_column(String(60), nullable=False)
    item: Mapped[str] = mapped_column(String(80), nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="visible", server_default="visible")
    priority: Mapped[int] = mapped_column(default=0, server_default="0")
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="explicit", server_default="explicit")


class FocusSession(TimestampMixin, Base):
    __tablename__ = "focus_sessions"
    __table_args__ = (
        Index("ix_focus_sessions_user_status", "user_id", "status"),
        Index("uq_focus_sessions_one_active_per_user", "user_id", unique=True, postgresql_where=text("status = 'active'"), sqlite_where=text("status = 'active'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"))
    objective: Mapped[str] = mapped_column(String(500), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    context_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")


class DriftEvent(CreatedAtMixin, Base):
    __tablename__ = "drift_events"
    __table_args__ = (Index("ix_drift_events_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"))
    focus_session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("focus_sessions.id", ondelete="SET NULL"))
    day_key: Mapped[str] = mapped_column(String(10), nullable=False)
    trigger_type: Mapped[DriftTrigger] = mapped_column(enum_column(DriftTrigger, "drift_trigger"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)


class DailyClose(TimestampMixin, Base):
    __tablename__ = "daily_closes"
    __table_args__ = (UniqueConstraint("user_id", "day_key", name="uq_daily_closes_user_day"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    day_key: Mapped[str] = mapped_column(String(10), nullable=False)
    done_list: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    drift_summary: Mapped[str | None] = mapped_column(Text)
    tomorrow_task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"))
    reflection: Mapped[str | None] = mapped_column(Text)


class DailyPlan(TimestampMixin, Base):
    __tablename__ = "daily_plans"
    __table_args__ = (UniqueConstraint("user_id", "day_key", name="uq_daily_plans_user_day"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    day_key: Mapped[str] = mapped_column(String(10), nullable=False)
    energy_level: Mapped[EnergyLevel | None] = mapped_column(enum_column(EnergyLevel, "daily_energy_level"))
    swapped_task_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")


class DailyPlanTask(Base):
    __tablename__ = "daily_plan_tasks"
    __table_args__ = (
        UniqueConstraint("plan_id", "task_id", name="uq_daily_plan_task"),
        UniqueConstraint("plan_id", "position", name="uq_daily_plan_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("daily_plans.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_anchor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")


class UserSettings(TimestampMixin, Base):
    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC", server_default="UTC")
    day_key: Mapped[str | None] = mapped_column(String(10))
    energy_today: Mapped[EnergyLevel | None] = mapped_column(enum_column(EnergyLevel, "user_energy_level"))
    preferred_anchor_time: Mapped[str | None] = mapped_column(String(5))
    quiet_hours: Mapped[dict[str, str] | None] = mapped_column(JSON)
    reduced_motion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    hide_timer_numbers: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    sound_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    haptics_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    theme: Mapped[str] = mapped_column(String(8), nullable=False, default="auto", server_default="auto")
    body_doubling_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    accountability_contact: Mapped[str | None] = mapped_column(String(240))
    default_energy: Mapped[EnergyLevel | None] = mapped_column(enum_column(EnergyLevel, "default_energy_level"))
    weekly_rest_day: Mapped[int | None] = mapped_column(Integer)
    check_in_interval: Mapped[int | None] = mapped_column(Integer)
    routines: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    last_seen_day_key: Mapped[str | None] = mapped_column(String(10))
    active_absence_key: Mapped[str | None] = mapped_column(String(10))
    dismissed_absence_key: Mapped[str | None] = mapped_column(String(10))
    prompt_state: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")


class IntegrationConnection(TimestampMixin, Base):
    __tablename__ = "integration_connections"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_integration_connection_user_provider"),
        Index("ix_integration_connections_provider", "provider", "last_successful_sync_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(120), nullable=False)
    account_login: Mapped[str] = mapped_column(String(120), nullable=False)
    credential_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    granted_scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    credential_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IntegrationOAuthState(CreatedAtMixin, Base):
    __tablename__ = "integration_oauth_states"
    __table_args__ = (
        UniqueConstraint("state_hash", name="uq_integration_oauth_state_hash"),
        Index("ix_integration_oauth_states_user_expiry", "user_id", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectIntegrationSource(CreatedAtMixin, Base):
    __tablename__ = "project_integration_sources"
    __table_args__ = (
        UniqueConstraint("project_id", "provider", name="uq_project_integration_source_project_provider"),
        Index("ix_project_integration_sources_user_provider", "user_id", "provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("integration_connections.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_resource_id: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_owner: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_name: Mapped[str] = mapped_column(String(160), nullable=False)
