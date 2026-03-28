"""Tool definitions for the LLM agent (OpenAI function calling format).

Each tool maps 1:1 to a WatiClient method. litellm translates this format
automatically for Anthropic and other providers.

This module is the single source of truth for tool metadata:
- WATI_TOOLS: OpenAI function-calling schemas
- TOOL_HTTP_MAP: tool → (HTTP method, endpoint template)
- TOOL_DISPATCH: tool → execution spec (API method, args, defaults)
- resolve_endpoint(): resolves endpoint templates from params
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

WATI_TOOLS: list[dict] = [
    # --- Contacts ---
    {
        "type": "function",
        "function": {
            "name": "get_contacts",
            "description": (
                "List contacts from WATI. Returns paginated contact list with names, "
                "phone numbers, segments, and custom attributes. Use this to find contacts "
                "before performing actions on them."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "page_size": {
                        "type": "integer",
                        "description": "Number of contacts per page (max 100)",
                        "default": 20,
                    },
                    "page_number": {
                        "type": "integer",
                        "description": "Page number (1-based)",
                        "default": 1,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_contact",
            "description": (
                "Get detailed information about a specific contact by phone number or ID."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": (
                            "Contact identifier: phone number (e.g. '5511999001122') or contact ID"
                        ),
                    },
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_contact",
            "description": "Add a new contact to WATI with name and optional custom attributes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "whatsapp_number": {
                        "type": "string",
                        "description": "WhatsApp number with country code (e.g. '5511999001122')",
                    },
                    "name": {
                        "type": "string",
                        "description": "Contact display name",
                    },
                    "custom_params": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "value": {"type": "string"},
                            },
                            "required": ["name", "value"],
                        },
                        "description": "Custom attributes (e.g. city, company)",
                    },
                },
                "required": ["whatsapp_number", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_contacts",
            "description": (
                "Update custom attributes of one or more contacts. "
                "Each update specifies a target (phone or ID) and the params to set."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "target": {
                                    "type": "string",
                                    "description": "Phone number or contact ID",
                                },
                                "custom_params": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "value": {"type": "string"},
                                        },
                                        "required": ["name", "value"],
                                    },
                                },
                            },
                            "required": ["target", "custom_params"],
                        },
                    },
                },
                "required": ["updates"],
            },
        },
    },
    # --- Tags ---
    {
        "type": "function",
        "function": {
            "name": "add_tag",
            "description": (
                "Add a tag to a contact. Tags are used for categorization and filtering."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Phone number of the contact (e.g. '6281234567890')",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Tag name to add (e.g. 'VIP', 'escalated')",
                    },
                },
                "required": ["target", "tag"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_tag",
            "description": "Remove a tag from a contact.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Phone number of the contact",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Tag name to remove",
                    },
                },
                "required": ["target", "tag"],
            },
        },
    },
    # --- Messages ---
    {
        "type": "function",
        "function": {
            "name": "send_text_message",
            "description": (
                "Send a text message to an active WhatsApp conversation. "
                "Requires an open session window (24h from last customer message)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Phone number or conversation ID",
                    },
                    "text": {
                        "type": "string",
                        "description": "Message text to send",
                    },
                },
                "required": ["target", "text"],
            },
        },
    },
    # --- Templates ---
    {
        "type": "function",
        "function": {
            "name": "get_templates",
            "description": (
                "List available WhatsApp message templates. "
                "Returns template names, IDs, status, and categories. "
                "Always call this to discover available templates before sending."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "page_size": {
                        "type": "integer",
                        "description": "Number of templates per page",
                        "default": 20,
                    },
                    "page_number": {
                        "type": "integer",
                        "description": "Page number (1-based)",
                        "default": 1,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_template_message",
            "description": (
                "Send a pre-approved WhatsApp template message to a contact. "
                "Use get_templates first to find the template name. "
                "IMPORTANT: Use the template NAME (elementName), not the ID. "
                "Custom params fill template variables (e.g. name, order_id)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {
                        "type": "string",
                        "description": (
                            "Template name (elementName from get_templates). "
                            "Use the NAME, not the ID."
                        ),
                    },
                    "target": {
                        "type": "string",
                        "description": "Recipient phone number or contact ID",
                    },
                    "custom_params": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "value": {"type": "string"},
                            },
                            "required": ["name", "value"],
                        },
                        "description": "Template variable values",
                    },
                },
                "required": ["template_id", "target"],
            },
        },
    },
    # --- Conversations ---
    {
        "type": "function",
        "function": {
            "name": "assign_operator",
            "description": "Assign an operator to handle a conversation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Phone number or conversation ID",
                    },
                    "operator_id": {
                        "type": "string",
                        "description": "Operator ID to assign",
                    },
                },
                "required": ["target", "operator_id"],
            },
        },
    },
    # --- Tickets ---
    {
        "type": "function",
        "function": {
            "name": "assign_ticket",
            "description": (
                "Assign a contact's conversation/ticket to a team. "
                "Use this to escalate or route conversations to specific teams like 'Support'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "whatsapp_number": {
                        "type": "string",
                        "description": "WhatsApp number of the contact",
                    },
                    "team_name": {
                        "type": "string",
                        "description": "Team to assign the ticket to (e.g. 'Support')",
                    },
                },
                "required": ["whatsapp_number", "team_name"],
            },
        },
    },
    # --- Operators ---
    {
        "type": "function",
        "function": {
            "name": "get_operators",
            "description": "List available operators/agents who can handle conversations.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    # --- Broadcasts ---
    {
        "type": "function",
        "function": {
            "name": "send_broadcast_to_segment",
            "description": (
                "Send a broadcast message using a template to all contacts "
                "in a specific segment. Use this for bulk messaging campaigns."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "template_name": {
                        "type": "string",
                        "description": "Template name to use for the broadcast",
                    },
                    "broadcast_name": {
                        "type": "string",
                        "description": "Name for this broadcast campaign",
                    },
                    "segment_name": {
                        "type": "string",
                        "description": "Segment to target (e.g. 'VIP', 'Premium')",
                    },
                },
                "required": ["template_name", "broadcast_name", "segment_name"],
            },
        },
    },
]

# Map tool name -> (HTTP method, endpoint template)
# Endpoint templates use {param_name} placeholders resolved from tool params.
TOOL_HTTP_MAP_V3: dict[str, tuple[str, str]] = {
    "get_contacts": ("GET", "/api/ext/v3/contacts"),
    "get_contact": ("GET", "/api/ext/v3/contacts/{target}"),
    "add_contact": ("POST", "/api/ext/v3/contacts"),
    "update_contacts": ("PUT", "/api/ext/v3/contacts"),
    "assign_contact_teams": ("PUT", "/api/ext/v3/contacts/teams"),
    "add_tag": ("POST", "/api/ext/v3/addTag/{target}"),
    "remove_tag": ("DELETE", "/api/ext/v3/removeTag/{target}/{tag}"),
    "send_text_message": ("POST", "/api/ext/v3/conversations/messages/text"),
    "get_templates": ("GET", "/api/ext/v3/messageTemplates"),
    "send_template_message": ("POST", "/api/ext/v3/messageTemplates/send"),
    "assign_operator": ("PUT", "/api/ext/v3/conversations/{target}/operator"),
    "update_conversation_status": ("PUT", "/api/ext/v3/conversations/{target}/status"),
    "assign_ticket": ("POST", "/api/ext/v3/tickets/assign"),
    "get_operators": ("GET", "/api/ext/v3/operators"),
    "send_broadcast_to_segment": ("POST", "/api/ext/v3/sendBroadcastToSegment"),
    "get_broadcasts": ("GET", "/api/ext/v3/broadcasts"),
    "get_broadcast": ("GET", "/api/ext/v3/broadcasts/{broadcast_id}"),
    "get_channels": ("GET", "/api/ext/v3/channels"),
}

TOOL_HTTP_MAP_V1: dict[str, tuple[str, str]] = {
    "get_contacts": ("GET", "/api/v1/getContacts"),
    "get_contact": ("GET", "/api/v1/getContactInfo/{target}"),
    "add_contact": ("POST", "/api/v1/addContact/{whatsapp_number}"),
    "update_contacts": ("POST", "/api/v1/updateContactAttributes/{target}"),
    "add_tag": ("POST", "/api/v1/addTag/{target}"),
    "remove_tag": ("DELETE", "/api/v1/removeTag/{target}/{tag}"),
    "send_text_message": ("POST", "/api/v1/sendSessionMessage/{target}"),
    "get_templates": ("GET", "/api/v1/getMessageTemplates"),
    "send_template_message": ("POST", "/api/v1/sendTemplateMessage/{target}"),
    "assign_operator": ("POST", "/api/v1/assignOperator/{target}"),
    "assign_ticket": ("POST", "/api/v1/tickets/assign"),
    "get_operators": ("GET", "/api/v1/getOperators"),
    "send_broadcast_to_segment": ("POST", "/api/v1/sendBroadcastToSegment"),
}

# Default map — V1 is the primary API version
TOOL_HTTP_MAP = TOOL_HTTP_MAP_V1


@dataclass(frozen=True)
class ToolSpec:
    """Execution spec for a single tool: maps to a WatiClient method."""

    method: str
    args: tuple[str, ...] = ()
    defaults: dict[str, Any] = field(default_factory=dict)
    has_custom_params: bool = False


_PAGE_DEFAULTS: dict[str, Any] = {"page_size": 20, "page_number": 1}

TOOL_DISPATCH: dict[str, ToolSpec] = {
    "get_contacts": ToolSpec("get_contacts", defaults=_PAGE_DEFAULTS),
    "get_contact": ToolSpec("get_contact", ("target",)),
    "add_contact": ToolSpec("add_contact", ("whatsapp_number", "name"), has_custom_params=True),
    "update_contacts": ToolSpec("update_contacts", ("updates",)),
    "add_tag": ToolSpec("add_tag", ("target", "tag")),
    "remove_tag": ToolSpec("remove_tag", ("target", "tag")),
    "send_text_message": ToolSpec("send_text_message", ("target", "text")),
    "get_templates": ToolSpec("get_templates", defaults=_PAGE_DEFAULTS),
    "send_template_message": ToolSpec(
        "send_template_message", ("template_id", "target"), has_custom_params=True
    ),
    "assign_operator": ToolSpec("assign_operator", ("target", "operator_id")),
    "assign_ticket": ToolSpec("assign_ticket", ("whatsapp_number", "team_name")),
    "get_operators": ToolSpec("get_operators"),
    "send_broadcast_to_segment": ToolSpec(
        "send_broadcast_to_segment", ("template_name", "broadcast_name", "segment_name")
    ),
}


def resolve_endpoint(
    tool_name: str,
    params: dict[str, Any],
    http_map: dict[str, tuple[str, str]] | None = None,
) -> tuple[str, str]:
    """Return (HTTP method, resolved endpoint) for a tool call."""
    mapping = http_map or TOOL_HTTP_MAP
    method, template = mapping.get(tool_name, ("", ""))
    endpoint = template.format_map(defaultdict(lambda: "?", params)) if template else ""
    return method, endpoint
