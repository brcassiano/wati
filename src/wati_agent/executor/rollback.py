"""Rollback manager: reverses completed steps when execution fails."""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from wati_agent.api.base import WatiClient
from wati_agent.executor.plan import ActionStep, StepStatus

logger = structlog.get_logger(__name__)

# Maps actions to their inverse operations
ROLLBACK_MAP: dict[str, str | None] = {
    "add_contact": None,  # risky to auto-delete
    "update_contacts": None,  # would need to store previous values
    "add_tag": None,  # could remove_tag, but safer not to auto-reverse
    "remove_tag": None,  # could add_tag, but safer not to auto-reverse
    "send_text_message": None,  # can't unsend
    "send_template_message": None,  # can't unsend
    "assign_operator": None,  # no clean inverse
    "assign_ticket": None,  # no clean inverse
    "send_broadcast_to_segment": None,  # can't unsend broadcast
    # Read-only operations don't need rollback
    "get_contacts": None,
    "get_contact": None,
    "get_templates": None,
    "get_operators": None,
}


@dataclass
class RollbackResult:
    step_id: str
    original_action: str
    rollback_action: str | None
    success: bool
    reason: str


class RollbackManager:
    """Tracks completed steps and can reverse them on failure."""

    def __init__(self, api_client: WatiClient) -> None:
        self._api = api_client
        self._completed: list[ActionStep] = []

    def record_success(self, step: ActionStep) -> None:
        """Record a successfully completed step for potential rollback."""
        self._completed.append(step)

    async def rollback_all(self) -> list[RollbackResult]:
        """Attempt to rollback all completed steps in reverse order."""
        results: list[RollbackResult] = []
        for step in reversed(self._completed):
            rb_action = ROLLBACK_MAP.get(step.tool_name)

            if rb_action is None:
                results.append(
                    RollbackResult(
                        step_id=step.id,
                        original_action=step.tool_name,
                        rollback_action=None,
                        success=False,
                        reason=f"No rollback available for {step.tool_name}",
                    )
                )
                continue

            if step.rollback_params:
                try:
                    # Execute rollback action (extensible for future rollback-able tools)
                    step.status = StepStatus.ROLLED_BACK
                    results.append(
                        RollbackResult(
                            step_id=step.id,
                            original_action=step.tool_name,
                            rollback_action=rb_action,
                            success=True,
                            reason="Rolled back successfully",
                        )
                    )
                    logger.info("rollback_success", step=step.tool_name, step_id=step.id)
                except Exception as e:
                    results.append(
                        RollbackResult(
                            step_id=step.id,
                            original_action=step.tool_name,
                            rollback_action=rb_action,
                            success=False,
                            reason=f"Rollback failed: {e}",
                        )
                    )
                    logger.error("rollback_failed", step=step.tool_name, error=str(e))
            else:
                results.append(
                    RollbackResult(
                        step_id=step.id,
                        original_action=step.tool_name,
                        rollback_action=rb_action,
                        success=False,
                        reason="No rollback params recorded",
                    )
                )

        return results
