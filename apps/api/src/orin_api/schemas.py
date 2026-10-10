from __future__ import annotations

import uuid
from typing import Annotated, Literal
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from orin_api.models import Density, EnergyLevel, FocusState, ProjectStatus, TaskPriority, TaskStatus, Theme


class PreferencesRead(BaseModel):
    density: Density
    theme: Theme
    locale: str
    visible_capabilities: list[str]
    hidden_capabilities: list[str]
    pinned_capabilities: list[str]
    autonomy_mode: str = "balanced"
    custom_autonomy: dict[str, str] = Field(default_factory=dict)


class PreferencesUpdate(BaseModel):
    density: Density = Density.COMFORTABLE
    theme: Theme = Theme.LIGHT
    locale: str = Field(default="en", min_length=2, max_length=20)
    visible_capabilities: list[str] = Field(default_factory=lambda: ["home", "calendar", "tasks", "projects", "activity", "memories", "focus"])
    pinned_capabilities: list[str] = Field(default_factory=lambda: ["home", "tasks"])
    autonomy_mode: str = Field(default="balanced", pattern="^(conservative|balanced|automatic|custom)$")
    custom_autonomy: dict[str, str] = Field(default_factory=dict)


class CapabilityRead(BaseModel):
    code: str
    name: str
    description: str
    granted: bool
    visible: bool
    pinned: bool


ProjectName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
TaskTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]


class ProjectCreate(BaseModel):
    name: ProjectName
    description: str | None = None
    objective: str | None = Field(default=None, max_length=2000)


class ProjectUpdate(BaseModel):
    name: ProjectName | None = None
    description: str | None = None
    objective: str | None = Field(default=None, max_length=2000)
    status: ProjectStatus | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    objective: str | None = None
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime


class TaskCreate(BaseModel):
    title: TaskTitle
    description: str | None = None
    project_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.NORMAL
    due_at: datetime | None = None
    first_step: str | None = None
    why: str | None = None
    energy_level: EnergyLevel | None = None
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)
    is_anchor: bool = False
    trigger: str | None = Field(default=None, max_length=240)


class TaskUpdate(BaseModel):
    title: TaskTitle | None = None
    description: str | None = None
    project_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_at: datetime | None = None
    first_step: str | None = None
    why: str | None = None
    energy_level: EnergyLevel | None = None
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)
    is_anchor: bool | None = None
    trigger: str | None = Field(default=None, max_length=240)


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    project_id: uuid.UUID | None
    assignee_id: uuid.UUID | None
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime
    focus_state: FocusState | None = None
    first_step: str | None = None
    why: str | None = None
    energy_level: EnergyLevel | None = None
    estimated_minutes: int | None = None
    is_anchor: bool = False
    trigger: str | None = None
    last_touched_at: datetime | None = None
    decay_review_at: datetime | None = None
    skip_count_today: int = 0
    skip_day_key: str | None = None
    today_day_key: str | None = None
    today_position: int | None = None
    completed_at: datetime | None = None
    released_at: datetime | None = None


class UserSettingsUpdate(BaseModel):
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    reduced_motion: bool | None = None
    sound_enabled: bool | None = None
    haptics_enabled: bool | None = None
    theme: Literal["light", "dark", "auto"] | None = None


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    command_id: uuid.UUID | None
    execution_id: uuid.UUID | None = None
    approval_id: uuid.UUID | None = None
    worker_job_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None
    project_id: uuid.UUID | None
    task_id: uuid.UUID | None
    activity_type: str
    summary: str
    intent: str | None
    result_status: str
    severity: str = "info"
    source: str = "api"
    correlation_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict, validation_alias="metadata_json")
    created_at: datetime


class CommandCreate(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    conversation_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    attachment_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5)


class CommandResult(BaseModel):
    command_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    status: str
    intent: str | None = None
    result: dict[str, object] | list[dict[str, object]] | None = None
    message: str
    execution: dict[str, object] | None = None


class CommandHistoryRead(CommandResult):
    text: str
    created_at: datetime


class ConversationRead(BaseModel):
    id: uuid.UUID
    title: str
    task_id: uuid.UUID | None
    project_id: uuid.UUID | None
    objective: str | None
    summary: str | None = None
    pending_question: dict[str, object] | None = None
    updated_at: datetime


class ConversationUpdate(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]


class SearchResultRead(BaseModel):
    result_id: uuid.UUID
    kind: str
    command_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    text: str
    excerpt: str
    created_at: datetime
    title: str | None


class AttachmentRead(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID | None
    task_id: uuid.UUID | None
    filename: str
    media_type: str
    size_bytes: int
    created_at: datetime


class ApprovalDecision(BaseModel):
    approved: bool
    note: Annotated[str | None, StringConstraints(max_length=1000)] = None


class RegisterRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=15, max_length=128)]
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class ProfileUpdate(BaseModel):
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class EmailChange(BaseModel):
    current_password: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    new_email: EmailStr


class PasswordChange(BaseModel):
    current_password: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    new_password: Annotated[str, StringConstraints(min_length=15, max_length=128)]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str
    created_at: datetime


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
