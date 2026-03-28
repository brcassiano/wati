"""Tests for tool definitions and validation."""

from __future__ import annotations

from wati_agent.agent.tools import TOOL_DISPATCH, TOOL_HTTP_MAP, WATI_TOOLS


def test_all_tools_have_required_fields() -> None:
    for tool in WATI_TOOLS:
        assert tool["type"] == "function"
        fn = tool["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn
        assert fn["parameters"]["type"] == "object"


def test_tool_names_are_unique() -> None:
    names = [t["function"]["name"] for t in WATI_TOOLS]
    assert len(names) == len(set(names))


def test_tool_dispatch_and_http_map_coverage() -> None:
    """Every tool has a dispatch spec and HTTP map entry."""
    for tool in WATI_TOOLS:
        name = tool["function"]["name"]
        assert name in TOOL_DISPATCH, f"{name} missing from TOOL_DISPATCH"
        assert name in TOOL_HTTP_MAP, f"{name} missing from TOOL_HTTP_MAP"


def test_expected_tools_exist() -> None:
    names = {t["function"]["name"] for t in WATI_TOOLS}
    expected = {
        "get_contacts",
        "get_contact",
        "add_contact",
        "update_contacts",
        "add_tag",
        "remove_tag",
        "send_text_message",
        "get_templates",
        "send_template_message",
        "assign_operator",
        "assign_ticket",
        "get_operators",
        "send_broadcast_to_segment",
    }
    assert expected.issubset(names)
