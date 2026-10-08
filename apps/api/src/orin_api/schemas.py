from __future__ import annotations

import uuid
from typing import Annotated
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from orin_api.models import Density, ProjectStatus, TaskPriority, TaskStatus, Theme


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
    visible_capabilities: list[str] = Field(default_factory=lambda: ["home", "tasks"])
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


class ProjectUpdate(BaseModel):
    name: ProjectName | None = None
    description: str | None = None
    status: ProjectStatus | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
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


class TaskUpdate(BaseModel):
    title: TaskTitle | None = None
    description: str | None = None
    project_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_at: datetime | None = None


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


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    command_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    project_id: uuid.UUID | None
    task_id: uuid.UUID | None
    activity_type: str
    summary: str
    intent: str | None
    result_status: str
    created_at: datetime


class CommandCreate(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class CommandResult(BaseModel):
    command_id: uuid.UUID
    status: str
    intent: str | None = None
    result: dict[str, object] | list[dict[str, object]] | None = None
    message: str
    execution: dict[str, object] | None = None


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
