"""Plan execution engine with step-by-step control."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from wati_agent.agent.tools import resolve_endpoint
from wati_agent.executor.plan import ActionPlan, ActionStep, StepStatus
from wati_agent.executor.validator import validate_steps
from wati_agent.observability.audit import AuditLogger


class PlanExecutor:
    """Executes an ActionPlan step-by-step with audit logging.

    Receives a tool_executor callable from the agent — does NOT duplicate
    tool dispatch logic.
    """

    def __init__(
        self,
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
        audit: AuditLogger,
        session_id: str,
        http_map: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        self._execute = tool_executor
        self._audit = audit
        self._session_id = session_id
        self._http_map = http_map

    def build_plan(
        self,
        pending_writes: list[tuple[str, dict[str, Any]]],
        description: str = "",
    ) -> ActionPlan:
        """Convert raw pending writes into a validated ActionPlan."""
        steps = [ActionStep(tool_name=name, params=params) for name, params in pending_writes]

        plan = ActionPlan(
            session_id=self._session_id,
            description=description,
            steps=steps,
        )

        # Validate all steps — mark invalid ones as FAILED
        validation = validate_steps(steps)
        if not validation.valid:
            for error_msg in validation.errors:
                # Error format: "Step N (tool_name): error"
                parts = error_msg.split(":", 1)
                if len(parts) == 2:
                    # Extract step index from "Step N"
                    try:
                        step_num = int(parts[0].split()[1]) - 1
                        if 0 <= step_num < len(steps):
                            steps[step_num].status = StepStatus.FAILED
                            steps[step_num].error = parts[1].strip()
                    except (IndexError, ValueError):
                        pass

        return plan

    async def execute_step(self, step: ActionStep, plan_id: str = "") -> ActionStep:
        """Execute a single step. Updates step in-place with result/status/duration."""
        method, endpoint = resolve_endpoint(step.tool_name, step.params, self._http_map)

        step.status = StepStatus.RUNNING
        start = time.monotonic()

        try:
            result = await self._execute(step.tool_name, step.params)
            step.status = StepStatus.SUCCESS
            step.result = result
            step.error = None
        except Exception as e:
            result = {"error": str(e)}
            step.status = StepStatus.FAILED
            step.result = result
            step.error = str(e)

        step.duration_ms = round((time.monotonic() - start) * 1000, 1)

        self._audit.log_action(
            session_id=self._session_id,
            action=step.tool_name,
            method=method,
            endpoint=endpoint,
            params=step.params,
            result=result,
            success=step.status == StepStatus.SUCCESS,
            duration_ms=step.duration_ms,
            error=step.error,
            plan_id=plan_id,
            step_id=step.id,
        )

        return step

    def skip_step(self, step: ActionStep) -> None:
        """Mark a step as skipped."""
        step.status = StepStatus.SKIPPED
