"""Tests for SlackNotifier."""

from __future__ import annotations

import json

import httpx
import pytest

from wati_agent.webhook.slack import SlackNotifier
from wati_agent.webhook.status_store import MessageStatusRecord


def _make_record(**overrides: object) -> MessageStatusRecord:
    defaults = {
        "message_id": "msg-test-123",
        "current_status": "failed",
        "status_history": [],
        "original_action": "send_text_message",
        "session_id": "session-abc-12345678",
        "target": "5511999887766",
    }
    defaults.update(overrides)
    return MessageStatusRecord(**defaults)


class TestSlackNotifier:
    @pytest.mark.asyncio
    async def test_notify_success(self) -> None:
        """Slack webhook returns 200 — notification succeeds."""
        captured: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, text="ok")

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        notifier = SlackNotifier("https://hooks.slack.com/test", http_client=client)

        record = _make_record()
        result = await notifier.notify_failure(
            record, error_code="470", error_message="Undeliverable"
        )

        assert result is True
        assert len(captured) == 1

        body = json.loads(captured[0].content)
        assert "blocks" in body
        assert any("Message Delivery Failed" in str(b) for b in body["blocks"])
        assert any("470" in str(b) for b in body["blocks"])

    @pytest.mark.asyncio
    async def test_notify_without_error_details(self) -> None:
        """No error_code or error_message — still sends notification."""
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="ok")

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        notifier = SlackNotifier("https://hooks.slack.com/test", http_client=client)

        result = await notifier.notify_failure(_make_record())
        assert result is True

    @pytest.mark.asyncio
    async def test_notify_slack_error_returns_false(self) -> None:
        """Slack returns 500 — fire-and-forget, returns False."""
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Internal Server Error")

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        notifier = SlackNotifier("https://hooks.slack.com/test", http_client=client)

        result = await notifier.notify_failure(_make_record())
        assert result is False

    @pytest.mark.asyncio
    async def test_notify_network_error_returns_false(self) -> None:
        """Network error — fire-and-forget, returns False."""
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        notifier = SlackNotifier("https://hooks.slack.com/test", http_client=client)

        result = await notifier.notify_failure(_make_record())
        assert result is False

    @pytest.mark.asyncio
    async def test_close_owned_client(self) -> None:
        """When SlackNotifier owns the client, close() shuts it down."""
        notifier = SlackNotifier("https://hooks.slack.com/test")
        await notifier.close()  # should not raise

    @pytest.mark.asyncio
    async def test_close_external_client_not_closed(self) -> None:
        """When an external client is provided, close() does not close it."""
        client = httpx.AsyncClient()
        notifier = SlackNotifier("https://hooks.slack.com/test", http_client=client)
        await notifier.close()
        # Client should still be usable
        assert not client.is_closed
        await client.aclose()
