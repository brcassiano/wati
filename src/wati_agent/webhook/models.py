"""Pydantic models for incoming WATI webhook payloads."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class MessageStatus(str, Enum):
    """Possible message delivery statuses from WATI webhooks."""

    sent = "sent"
    delivered = "delivered"
    read = "read"
    failed = "failed"


class WebhookStatusPayload(BaseModel):
    """Incoming WATI webhook payload for message status updates."""

    event_type: str
    message_id: str
    status: MessageStatus
    timestamp: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None

    model_config = {"extra": "ignore"}


class WebhookResponse(BaseModel):
    """Standard response returned to WATI webhook caller."""

    ok: bool = True
    message: str = "accepted"
    error: str | None = None
