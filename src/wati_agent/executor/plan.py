"""Action plan models for tracking execution state."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"


class ActionStep(BaseModel):
    """A single step in an execution plan."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    tool_name: str
    params: dict[str, Any] = Field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    result: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float | None = None
    rollback_action: str | None = None
    rollback_params: dict[str, Any] | None = None


class ActionPlan(BaseModel):
    """A multi-step execution plan."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    session_id: str = ""
    description: str = ""
    steps: list[ActionStep] = Field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def completed_steps(self) -> list[ActionStep]:
        return [s for s in self.steps if s.status == StepStatus.SUCCESS]

    @property
    def failed_steps(self) -> list[ActionStep]:
        return [s for s in self.steps if s.status == StepStatus.FAILED]

    @property
    def pending_steps(self) -> list[ActionStep]:
        return [s for s in self.steps if s.status == StepStatus.PENDING]

    @property
    def skipped_steps(self) -> list[ActionStep]:
        return [s for s in self.steps if s.status == StepStatus.SKIPPED]

    @property
    def summary(self) -> str:
        return (
            f"{len(self.completed_steps)} succeeded, "
            f"{len(self.failed_steps)} failed, "
            f"{len(self.skipped_steps)} skipped"
        )
