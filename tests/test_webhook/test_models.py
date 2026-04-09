"""Tests for webhook Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from wati_agent.webhook.models import MessageStatus, WebhookResponse, WebhookStatusPayload


class TestMessageStatus:
    def test_all_values(self) -> None:
        assert set(MessageStatus) == {
            MessageStatus.sent,
            MessageStatus.delivered,
            MessageStatus.read,
            MessageStatus.failed,
        }

    def test_string_value(self) -> None:
        assert MessageStatus.failed.value == "failed"
        assert str(MessageStatus.failed) == "MessageStatus.failed"


class TestWebhookStatusPayload:
    def test_valid_minimal(self) -> None:
        payload = WebhookStatusPayload(
            event_type="message_status_update",
            message_id="msg-123",
            status="delivered",
        )
        assert payload.message_id == "msg-123"
        assert payload.status == MessageStatus.delivered
        assert payload.timestamp is None
        assert payload.error_code is None

    def test_valid_full(self) -> None:
        payload = WebhookStatusPayload(
            event_type="message_status_update",
            message_id="msg-456",
            status="failed",
            timestamp="2026-04-08T12:00:00Z",
            error_code="470",
            error_message="Message undeliverable",
        )
        assert payload.status == MessageStatus.failed
        assert payload.error_code == "470"
        assert payload.timestamp is not None

    def test_extra_fields_ignored(self) -> None:
        payload = WebhookStatusPayload(
            event_type="message_status_update",
            message_id="msg-789",
            status="read",
            unknown_field="should be ignored",
            another_extra=42,
        )
        assert payload.message_id == "msg-789"
        assert not hasattr(payload, "unknown_field")

    def test_missing_required_field(self) -> None:
        with pytest.raises(ValidationError):
            WebhookStatusPayload(event_type="test", status="sent")  # missing message_id

    def test_invalid_status(self) -> None:
        with pytest.raises(ValidationError):
            WebhookStatusPayload(
                event_type="test",
                message_id="msg-000",
                status="invalid_status",
            )

    def test_from_dict(self) -> None:
        data = {
            "event_type": "message_status_update",
            "message_id": "msg-abc",
            "status": "sent",
        }
        payload = WebhookStatusPayload.model_validate(data)
        assert payload.status == MessageStatus.sent


class TestWebhookResponse:
    def test_defaults(self) -> None:
        resp = WebhookResponse()
        assert resp.ok is True
        assert resp.message == "accepted"
        assert resp.error is None

    def test_error_response(self) -> None:
        resp = WebhookResponse(ok=False, error="invalid json")
        assert resp.ok is False
        assert resp.error == "invalid json"
