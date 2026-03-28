"""Tests for PlanExecutor: build, execute, skip, validate."""

from __future__ import annotations

from pathlib import Path

import pytest

from wati_agent.agent.tools import TOOL_HTTP_MAP, WATI_TOOLS
from wati_agent.executor import PlanExecutor
from wati_agent.executor.plan import ActionPlan, ActionStep, StepStatus
from wati_agent.observability.audit import AuditLogger

# --- Fixtures ---


async def _mock_tool_executor(name: str, params: dict) -> dict:
    """Simulates successful tool execution."""
    return {"ok": True, "action": name, "params": params}


async def _failing_tool_executor(name: str, params: dict) -> dict:
    """Simulates a failing tool execution."""
    raise RuntimeError(f"API error for {name}")


@pytest.fixture
def executor(audit: AuditLogger) -> PlanExecutor:
    return PlanExecutor(
        tool_executor=_mock_tool_executor,
        audit=audit,
        session_id="test-session",
    )


@pytest.fixture
def failing_executor(audit: AuditLogger) -> PlanExecutor:
    return PlanExecutor(
        tool_executor=_failing_tool_executor,
        audit=audit,
        session_id="test-session",
    )


# --- build_plan ---


def test_build_plan_creates_steps(executor: PlanExecutor) -> None:
    pending = [
        ("send_text_message", {"target": "5511999", "text": "Hello"}),
        ("add_contact", {"whatsapp_number": "5511888", "name": "Test"}),
    ]
    plan = executor.build_plan(pending)

    assert isinstance(plan, ActionPlan)
    assert len(plan.steps) == 2
    assert plan.steps[0].tool_name == "send_text_message"
    assert plan.steps[0].params["target"] == "5511999"
    assert plan.steps[1].tool_name == "add_contact"
    assert plan.session_id == "test-session"


def test_build_plan_validates_steps(executor: PlanExecutor) -> None:
    pending = [
        ("send_text_message", {"target": "5511999"}),  # missing "text"
        ("add_contact", {"whatsapp_number": "5511888", "name": "Test"}),  # valid
    ]
    plan = executor.build_plan(pending)

    assert plan.steps[0].status == StepStatus.FAILED
    assert "Missing required parameter" in (plan.steps[0].error or "")
    assert plan.steps[1].status == StepStatus.PENDING


def test_build_plan_empty(executor: PlanExecutor) -> None:
    plan = executor.build_plan([])
    assert len(plan.steps) == 0


# --- execute_step ---


@pytest.mark.asyncio
async def test_execute_step_success(executor: PlanExecutor, audit: AuditLogger) -> None:
    step = ActionStep(tool_name="send_text_message", params={"target": "5511999", "text": "Hi"})

    result = await executor.execute_step(step, plan_id="plan-1")

    assert result.status == StepStatus.SUCCESS
    expected = {
        "ok": True,
        "action": "send_text_message",
        "params": {"target": "5511999", "text": "Hi"},
    }
    assert result.result == expected
    assert result.duration_ms is not None
    assert result.duration_ms >= 0
    assert result.error is None

    # Verify audit was logged
    entries = audit.get_session_entries("test-session")
    assert len(entries) == 1
    assert entries[0].action == "send_text_message"
    assert entries[0].method == "POST"
    assert entries[0].endpoint == "/api/v1/sendSessionMessage/5511999"
    assert entries[0].success is True
    assert entries[0].plan_id == "plan-1"
    assert entries[0].step_id == step.id


@pytest.mark.asyncio
async def test_execute_step_failure(failing_executor: PlanExecutor, audit: AuditLogger) -> None:
    params = {"whatsapp_number": "5511999", "name": "Test"}
    step = ActionStep(tool_name="add_contact", params=params)

    result = await failing_executor.execute_step(step)

    assert result.status == StepStatus.FAILED
    assert "API error" in (result.error or "")
    assert result.result == {"error": "API error for add_contact"}

    entries = audit.get_session_entries("test-session")
    assert len(entries) == 1
    assert entries[0].success is False


@pytest.mark.asyncio
async def test_execute_step_resolves_endpoint(executor: PlanExecutor, audit: AuditLogger) -> None:
    params = {"target": "5511999", "operator_id": "op-1"}
    step = ActionStep(tool_name="assign_operator", params=params)

    await executor.execute_step(step)

    entries = audit.get_session_entries("test-session")
    assert entries[0].endpoint == "/api/v1/assignOperator/5511999"
    assert entries[0].method == "POST"


# --- skip_step ---


def test_skip_step(executor: PlanExecutor) -> None:
    step = ActionStep(tool_name="send_text_message", params={"target": "5511999", "text": "Hi"})
    executor.skip_step(step)
    assert step.status == StepStatus.SKIPPED


# --- ActionPlan properties ---


def test_plan_summary() -> None:
    plan = ActionPlan(
        steps=[
            ActionStep(tool_name="a", status=StepStatus.SUCCESS),
            ActionStep(tool_name="b", status=StepStatus.FAILED),
            ActionStep(tool_name="c", status=StepStatus.SKIPPED),
            ActionStep(tool_name="d", status=StepStatus.SUCCESS),
        ]
    )

    assert len(plan.completed_steps) == 2
    assert len(plan.failed_steps) == 1
    assert len(plan.skipped_steps) == 1
    assert plan.summary == "2 succeeded, 1 failed, 1 skipped"


# --- TOOL_HTTP_MAP completeness ---


def test_tool_http_map_covers_all_tools() -> None:
    tool_names = {t["function"]["name"] for t in WATI_TOOLS}
    mapped_names = set(TOOL_HTTP_MAP.keys())
    missing = tool_names - mapped_names
    extra = mapped_names - tool_names
    assert tool_names == mapped_names, f"Missing: {missing}, Extra: {extra}"


def test_tool_http_map_values_are_valid() -> None:
    for tool_name, (method, endpoint) in TOOL_HTTP_MAP.items():
        assert method in ("GET", "POST", "PUT", "DELETE"), f"{tool_name}: invalid method {method}"
        assert endpoint.startswith("/"), f"{tool_name}: endpoint should start with /"


# --- Audit enrichment ---


def test_audit_entry_new_fields(tmp_path: Path) -> None:
    audit = AuditLogger(audit_file=tmp_path / "audit.jsonl")
    entry = audit.log_action(
        session_id="s1",
        action="send_text_message",
        method="POST",
        endpoint="/conversations/messages/text",
        params={"target": "5511999", "text": "Hi"},
        result={"ok": True},
        success=True,
        duration_ms=42.0,
        plan_id="plan-1",
        step_id="step-1",
    )

    assert entry.method == "POST"
    assert entry.endpoint == "/conversations/messages/text"
    assert entry.result == {"ok": True}
    assert entry.plan_id == "plan-1"
    assert entry.step_id == "step-1"
    assert entry.dry_run is False
