"""Trusted action registry and execution policy boundary."""
from __future__ import annotations

import uuid
import re
import json
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Callable, Mapping, Type

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from orin_api.models import Approval, ApprovalStatus, Command, CommandStatus, ExecutionAudit


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Reversibility(StrEnum):
    REVERSIBLE = "reversible"
    PARTIAL = "partially_reversible"
    IRREVERSIBLE = "irreversible"


class ActionStatus(StrEnum):
    EXECUTED = "executed"
    PENDING_APPROVAL = "pending_approval"
    DENIED = "denied"
    FAILED = "failed"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


class StrictActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    inputs: dict[str, Any]


@dataclass(frozen=True)
class ActionContext:
    session: Session
    user_id: uuid.UUID
    command_id: uuid.UUID
    permissions: frozenset[str]
    approval_id: uuid.UUID | None = None
    command_text: str = ""


ActionHandler = Callable[[ActionContext, BaseModel], dict[str, Any] | list[dict[str, Any]] | None]
ApprovalPolicy = Callable[["ActionDefinition"], bool]


@dataclass(frozen=True)
class ActionDefinition:
    name: str
    input_schema: Type[StrictActionInput]
    permission: str
    risk_level: RiskLevel
    handler: ActionHandler
    reversibility: Reversibility
    requires_approval: bool = False


class ActionRegistry:
    def __init__(self, definitions: list[ActionDefinition] | tuple[ActionDefinition, ...]):
        items: dict[str, ActionDefinition] = {}
        for definition in definitions:
            if definition.name in items:
                raise ValueError(f"Duplicate action definition: {definition.name}")
            if not re.fullmatch(r"[a-z][a-z0-9_]*", definition.name) or not definition.permission:
                raise ValueError("Action name and permission are required")
            if not isinstance(definition.risk_level, RiskLevel) or not isinstance(definition.reversibility, Reversibility):
                raise TypeError("Action risk and reversibility must use trusted metadata enums")
            if not isinstance(definition.input_schema, type) or not issubclass(definition.input_schema, StrictActionInput):
                raise TypeError("Action input schema must be a StrictActionInput model")
            if not callable(definition.handler):
                raise TypeError("Action handler must be callable")
            items[definition.name] = definition
        self._definitions: Mapping[str, ActionDefinition] = MappingProxyType(items)

    def get(self, name: str) -> ActionDefinition | None:
        return self._definitions.get(name)

    def all(self) -> tuple[ActionDefinition, ...]:
        return tuple(self._definitions.values())


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    action: str
    status: ActionStatus
    result: dict[str, Any] | list[dict[str, Any]] | None = None
    error: str | None = None
    approval_required: bool = False
    approval_id: uuid.UUID | None = None
    audit_id: uuid.UUID | None = None


class ActionExecutionError(Exception):
    """Safe, intentional failure raised by a registered handler."""

    def __init__(self, message: str, *, status: ActionStatus = ActionStatus.FAILED):
        super().__init__(message)
        self.status = status


class ExecutionEngine:
    def __init__(self, registry: ActionRegistry, approval_policy: ApprovalPolicy | None = None):
        self.registry = registry
        self.approval_policy = approval_policy or (lambda definition: definition.requires_approval)

    def execute(self, request: ActionRequest, context: ActionContext) -> ExecutionResult:
        definition = self.registry.get(request.action)
        if definition is None:
            return self._audit(context, request.action, None, None, ActionStatus.UNSUPPORTED, "Action is not supported.")
        try:
            # Treat action payloads as JSON at the boundary. Strict JSON validation
            # still rejects coercions while allowing standard UUID/date encodings.
            inputs = definition.input_schema.model_validate_json(json.dumps(request.inputs, default=str))
        except ValidationError:
            return self._audit(context, definition.name, definition, None, ActionStatus.INVALID, "Action inputs are invalid.")
        if definition.permission not in context.permissions:
            return self._audit(context, definition.name, definition, inputs, ActionStatus.DENIED, "You do not have permission to perform this action.")

        approval_id: uuid.UUID | None = None
        if self.approval_policy(definition):
            approval = context.session.get(Approval, context.approval_id) if context.approval_id else None
            valid_approval = (
                approval is not None
                and approval.status == ApprovalStatus.APPROVED
                and approval.requested_by_id == context.user_id
                and approval.command_id == context.command_id
                and approval.action_name == definition.name
                and approval.action_payload == inputs.model_dump(mode="json")
            )
            if not valid_approval:
                if approval is not None:
                    return self._audit(context, definition.name, definition, inputs, ActionStatus.DENIED, "Approval is invalid or does not match this action.")
                approval = Approval(
                    command_id=context.command_id,
                    requested_by_id=context.user_id,
                    status=ApprovalStatus.PENDING,
                    action_name=definition.name,
                    action_payload=inputs.model_dump(mode="json"),
                    risk_level=definition.risk_level.value,
                    permission=definition.permission,
                    reversible=definition.reversibility != Reversibility.IRREVERSIBLE,
                )
                context.session.add(approval)
                command = context.session.get(Command, context.command_id)
                if command:
                    command.status = CommandStatus.AWAITING_APPROVAL
                return self._audit(context, definition.name, definition, inputs, ActionStatus.PENDING_APPROVAL, "This action requires approval before it can run.", approval=approval)
            approval_id = approval.id

        try:
            result = definition.handler(context, inputs)
        except ActionExecutionError as exc:
            return self._audit(context, definition.name, definition, inputs, exc.status, str(exc), approval_id=approval_id)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Registered action handler failed", extra={"action": definition.name})
            return self._audit(context, definition.name, definition, inputs, ActionStatus.FAILED, "The action could not be completed.", approval_id=approval_id)
        result_approval_id = None
        if isinstance(result, dict) and result.get("approval_id"):
            try:
                result_approval_id = uuid.UUID(str(result["approval_id"]))
            except ValueError:
                result_approval_id = None
        if isinstance(result, dict) and result.get("status") == "pending_approval":
            approval = context.session.get(Approval, result_approval_id) if result_approval_id else None
            return self._audit(context, definition.name, definition, inputs, ActionStatus.PENDING_APPROVAL, "This action requires approval before it can run.", result=result, approval=approval)
        return self._audit(context, definition.name, definition, inputs, ActionStatus.EXECUTED, None, result=result, approval_id=approval_id or result_approval_id)

    @staticmethod
    def _audit(
        context: ActionContext,
        action: str,
        definition: ActionDefinition | None,
        inputs: StrictActionInput | None,
        status: ActionStatus,
        error: str | None = None,
        *,
        result: dict[str, Any] | list[dict[str, Any]] | None = None,
        approval: Approval | None = None,
        approval_id: uuid.UUID | None = None,
    ) -> ExecutionResult:
        row = ExecutionAudit(
            user_id=context.user_id,
            command_id=context.command_id,
            action_name=action,
            risk_level=definition.risk_level.value if definition else "low",
            permission=definition.permission if definition else "unknown",
            approval_required=bool(definition and (definition.requires_approval or status == ActionStatus.PENDING_APPROVAL)),
            execution_status=status.value,
            result_status="succeeded" if status == ActionStatus.EXECUTED else status.value,
            entity_type=str(result.get("entity_type")) if isinstance(result, dict) and result.get("entity_type") else None,
            entity_id=str(result.get("id")) if isinstance(result, dict) and result.get("id") else None,
            approval_id=approval.id if approval else approval_id,
        )
        context.session.add(row)
        context.session.flush()
        return ExecutionResult(
            success=status == ActionStatus.EXECUTED,
            action=action,
            status=status,
            result=result,
            error=error,
            approval_required=status == ActionStatus.PENDING_APPROVAL,
            approval_id=approval.id if approval else approval_id,
            audit_id=row.id,
        )
