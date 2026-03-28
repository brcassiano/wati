"""Tests for the rollback manager."""

from __future__ import annotations

import pytest

from wati_agent.api.mock import MockWatiClient
from wati_agent.executor.plan import ActionStep, StepStatus
from wati_agent.executor.rollback import RollbackManager


@pytest.fixture
def manager() -> RollbackManager:
    return RollbackManager(MockWatiClient())


@pytest.mark.asyncio
async def test_rollback_with_no_steps(manager: RollbackManager) -> None:
    results = await manager.rollback_all()
    assert results == []


@pytest.mark.asyncio
async def test_rollback_irreversible_action(manager: RollbackManager) -> None:
    step = ActionStep(
        tool_name="send_template_message",
        params={"template_id": "t1", "target": "5511999001122"},
        status=StepStatus.SUCCESS,
    )
    manager.record_success(step)
    results = await manager.rollback_all()
    assert len(results) == 1
    assert results[0].success is False
    assert "No rollback available" in results[0].reason


@pytest.mark.asyncio
async def test_rollback_add_tag_irreversible(manager: RollbackManager) -> None:
    step = ActionStep(
        tool_name="add_tag",
        params={"target": "5511999001122", "tag": "VIP"},
        status=StepStatus.SUCCESS,
    )
    manager.record_success(step)
    results = await manager.rollback_all()
    assert len(results) == 1
    assert results[0].success is False
    assert "No rollback available" in results[0].reason
