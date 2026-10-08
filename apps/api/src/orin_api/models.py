from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
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
    ACTIVE = "active"
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


def enum_column(enum_class: type[enum.Enum], name: str) -> Enum:
    return Enum(
        enum_class,
        name=name,
        values_callable=lambda members: [member.value for member in members],
        native_enum=True,
        validate_strings=True,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


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
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(enum_column(ProjectStatus, "project_status"), nullable=False, default=ProjectStatus.ACTIVE, server_default=ProjectStatus.ACTIVE.value)

    owner: Mapped[User] = relationship(back_populates="projects")
    members: Mapped[list[ProjectMember]] = relationship(back_populates="project", cascade="all, delete-orphan")
    tasks: Mapped[list[Task]] = relationship(back_populates="project")


class ProjectMember(TimestampMixin, Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[ProjectRole] = mapped_column(enum_column(ProjectRole, "project_role"), nullable=False, default=ProjectRole.VIEWER, server_default=ProjectRole.VIEWER.value)

    project: Mapped[Project] = relationship(back_populates="members")


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_owner_status_due", "owner_id", "status", "due_at"),
        Index("ix_tasks_project_status", "project_id", "status"),
        Index("ix_tasks_assignee_status", "assignee_id", "status"),
        CheckConstraint("length(trim(title)) > 0", name="ck_tasks_title_nonempty"),
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


class Command(TimestampMixin, Base):
    __tablename__ = "commands"
    __table_args__ = (Index("ix_commands_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"))
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CommandStatus] = mapped_column(enum_column(CommandStatus, "command_status"), nullable=False, default=CommandStatus.SUBMITTED, server_default=CommandStatus.SUBMITTED.value)


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
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    command_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("commands.id", ondelete="SET NULL"))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"))
    activity_type: Mapped[ActivityType] = mapped_column(enum_column(ActivityType, "activity_type"), nullable=False)
    summary: Mapped[str] = mapped_column(String(240), nullable=False)
    intent: Mapped[str | None] = mapped_column(String(40))
    result_status: Mapped[str] = mapped_column(String(20), nullable=False, default="succeeded", server_default="succeeded")


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
