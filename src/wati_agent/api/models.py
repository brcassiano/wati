"""Pydantic models for WATI API payloads."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# --- Common ---


class CustomParam(BaseModel):
    """Key-value custom parameter used across contacts and templates."""

    name: str
    value: str


class ApiError(BaseModel):
    """Standard error response from WATI API."""

    code: int = 0
    message: str = ""
    timestamp: datetime | None = None


# --- Contacts ---


class ContactLink(BaseModel):
    """Cross-platform contact identifiers."""

    whats_app_contact_id: str | None = None
    instagram_contact_id: str | None = None
    messenger_contact_id: str | None = None


class Contact(BaseModel):
    """Single contact record from WATI API V3."""

    id: str = ""
    wa_id: str | None = None
    name: str = ""
    phone: str = ""
    photo: str | None = None
    created: datetime | None = None
    last_updated: datetime | None = None
    contact_status: str | None = None
    source: str | None = None
    channel_id: str | None = None
    opted_in: bool = False
    allow_broadcast: bool = False
    allow_sms: bool = False
    tags: list[str] = Field(default_factory=list)
    teams: list[str] = Field(default_factory=list)
    segments: list[str] = Field(default_factory=list)
    custom_params: list[CustomParam] = Field(default_factory=list)
    channel_type: str | None = None
    display_name: str | None = None
    contact_link: ContactLink | None = None
    is_broadcast_limit_reached: str | None = None


class ContactListResponse(BaseModel):
    """GET /api/ext/v3/contacts response."""

    contact_list: list[Contact] = Field(default_factory=list)
    page_number: int = 1
    page_size: int = 20


# --- Templates ---


class MessageTemplate(BaseModel):
    """Single message template record."""

    id: str = ""
    name: str = ""
    status: str = ""
    category: str | None = None
    language: str | None = None
    body: str | None = None
    custom_params: list[CustomParam] = Field(default_factory=list)
    created: datetime | None = None
    last_updated: datetime | None = None


class TemplateListResponse(BaseModel):
    """GET /api/ext/v3/messageTemplates response."""

    template_list: list[MessageTemplate] = Field(default_factory=list)
    page_number: int = 1
    page_size: int = 20
    total: int = 0


class SendTemplateRequest(BaseModel):
    """POST /api/ext/v3/messageTemplates/send request body."""

    template_id: str
    target: str
    custom_params: list[CustomParam] = Field(default_factory=list)


class SendTemplateResponse(BaseModel):
    """POST /api/ext/v3/messageTemplates/send response."""

    result: bool = False
    message_id: str | None = None
    status: str | None = None


# --- Messages ---


class SendTextRequest(BaseModel):
    """POST /api/ext/v3/conversations/messages/text request body."""

    target: str
    text: str


class SendTextResponse(BaseModel):
    """POST /api/ext/v3/conversations/messages/text response."""

    id: str | None = None
    created: datetime | None = None
    conversation_id: str | None = None
    ticket_id: str | None = None
    event_type: str | None = None


# --- Conversations ---


class AssignOperatorRequest(BaseModel):
    """PUT /api/ext/v3/conversations/{target}/operator request body."""

    operator_id: str


class UpdateStatusRequest(BaseModel):
    """PUT /api/ext/v3/conversations/{target}/status request body."""

    status: str  # e.g. "open", "closed"


# --- Contacts Update ---


class ContactUpdateItem(BaseModel):
    """Single contact update entry for batch update."""

    target: str
    custom_params: list[CustomParam] = Field(default_factory=list, alias="customParams")

    model_config = {"populate_by_name": True}


class ContactUpdateRequest(BaseModel):
    """PUT /api/ext/v3/contacts request body."""

    contacts: list[ContactUpdateItem]


class AssignTeamRequest(BaseModel):
    """PUT /api/ext/v3/contacts/teams request body."""

    target: str
    teams: list[str]


# --- Broadcasts ---


class Broadcast(BaseModel):
    """Single broadcast/campaign record."""

    id: str = ""
    channel_id: str | None = None
    name: str = ""
    status: str = ""
    template_id: str | None = None
    created: datetime | None = None
    last_updated: datetime | None = None
    scheduled_at: datetime | None = None


class BroadcastStatistics(BaseModel):
    """Broadcast delivery statistics."""

    total_recipients: int = 0
    total_sent: int = 0
    total_delivered: int = 0
    total_read: int = 0
    total_replied: int = 0
    total_failed: int = 0


class BroadcastDetail(BaseModel):
    """GET /api/ext/v3/broadcasts/{id} response."""

    id: str = ""
    channel_id: str | None = None
    name: str = ""
    status: str = ""
    template_id: str | None = None
    statistics: BroadcastStatistics | None = None


class BroadcastListResponse(BaseModel):
    """GET /api/ext/v3/broadcasts response."""

    broadcasts: list[Broadcast] = Field(default_factory=list)
    page_number: int = 1
    page_size: int = 20
    total: int = 0


# --- Channels ---


class Channel(BaseModel):
    """Channel record."""

    id: str = ""
    name: str = ""
    phone: str | None = None
    channel_type: str | None = None


class ChannelListResponse(BaseModel):
    """GET /api/ext/v3/channels response."""

    channels: list[Channel] = Field(default_factory=list)


# --- Generic API Response ---


class ApiResponse(BaseModel):
    """Generic success/failure response."""

    result: bool = True
    message: str | None = None
    data: dict | None = None
