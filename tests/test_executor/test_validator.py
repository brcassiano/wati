"""Tests for the action step validator."""

from __future__ import annotations

from wati_agent.executor.plan import ActionStep
from wati_agent.executor.validator import validate_step, validate_steps


def test_valid_step() -> None:
    step = ActionStep(tool_name="get_contact", params={"target": "5511999001122"})
    result = validate_step(step)
    assert result.valid
    assert not result.errors


def test_missing_required_param() -> None:
    step = ActionStep(tool_name="get_contact", params={})
    result = validate_step(step)
    assert not result.valid
    assert "target" in result.errors[0]


def test_unknown_tool() -> None:
    step = ActionStep(tool_name="nonexistent_tool", params={})
    result = validate_step(step)
    assert not result.valid
    assert "Unknown tool" in result.errors[0]


def test_optional_params_are_fine() -> None:
    step = ActionStep(tool_name="get_contacts", params={})
    result = validate_step(step)
    assert result.valid


def test_validate_multiple_steps() -> None:
    steps = [
        ActionStep(tool_name="get_contacts", params={}),
        ActionStep(tool_name="send_template_message", params={"template_id": "t1"}),
    ]
    result = validate_steps(steps)
    assert not result.valid  # second step missing "target"
    assert any("target" in e for e in result.errors)


def test_validate_all_valid() -> None:
    steps = [
        ActionStep(tool_name="get_contacts", params={}),
        ActionStep(tool_name="get_templates", params={}),
    ]
    result = validate_steps(steps)
    assert result.valid
