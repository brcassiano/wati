"""Integration tests for the webhook Starlette app."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from wati_agent.observability.audit import AuditLogger
from wati_agent.webhook.app import create_webhook_app
from wati_agent.webhook.slack import SlackNotifier
from wati_agent.webhook.status_store import MessageStatusStore


@pytest.fixture
def audit(tmp_path: Path) -> AuditLogger:
    return AuditLogger(audit_file=tmp_path / "audit.jsonl")


@pytest.fixture
def store(audit: AuditLogger, tmp_path: Path) -> MessageStatusStore:
    return MessageStatusStore(audit=audit, persist_path=tmp_path / "status.jsonl")


@pytest.fixture
def slack_mock() -> SlackNotifier:
    """SlackNotifier with mocked notify_failure."""
    notifier = SlackNotifier.__new__(SlackNotifier)
    notifier.notify_failure = AsyncMock(return_value=True)
    notifier.close = AsyncMock()
    return notifier


@pytest.fixture
def app(store: MessageStatusStore, slack_mock: SlackNotifier, audit: AuditLogger):
    return create_webhook_app(store, slack_mock, audit)


@pytest.fixture
def app_no_slack(store: MessageStatusStore, audit: AuditLogger):
    return create_webhook_app(store, slack=None, audit=audit)


def _valid_payload(message_id: str = "msg-100", status: str = "delivered") -> dict:
    return {
        "event_type": "message_status_update",
        "message_id": message_id,
        "status": status,
    }


class TestStatusWebhook:
    @pytest.mark.asyncio
    async def test_valid_status_update(self, app, store: MessageStatusStore) -> None:
        store.register_message("msg-100", "send_text_message", "s1", "5511999")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/webhook/status", json=_valid_payload())

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["message"] == "accepted"

        record = store.get("msg-100")
        assert record is not None
        assert record.current_status == "delivered"

    @pytest.mark.asyncio
    async def test_invalid_json(self, app) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/webhook/status",
                content=b"not json",
                headers={"content-type": "application/json"},
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is False
        assert "invalid json" in resp.json()["error"]

    @pytest.mark.asyncio
    async def test_validation_error(self, app) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/webhook/status",
                json={"event_type": "test"},  # missing required fields
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is False
        assert "invalid payload" in resp.json()["error"]

    @pytest.mark.asyncio
    async def test_unknown_message_id(self, app) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/webhook/status", json=_valid_payload("unknown-id"))

        assert resp.status_code == 200
        assert resp.json()["message"] == "unknown message_id"

    @pytest.mark.asyncio
    async def test_duplicate_event(self, app, store: MessageStatusStore) -> None:
        store.register_message("msg-100", "send_text_message", "s1", "5511999")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/webhook/status", json=_valid_payload())
            resp = await client.post("/webhook/status", json=_valid_payload())

        assert resp.status_code == 200
        assert resp.json()["message"] == "duplicate"

    @pytest.mark.asyncio
    async def test_failed_status_triggers_slack(
        self, app, store: MessageStatusStore, slack_mock: SlackNotifier
    ) -> None:
        store.register_message("msg-100", "send_text_message", "s1", "5511999")

        payload = _valid_payload(status="failed")
        payload["error_code"] = "470"
        payload["error_message"] = "Undeliverable"

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/webhook/status", json=payload)

        # Let the fire-and-forget task complete
        await asyncio.sleep(0)

        assert resp.status_code == 200
        slack_mock.notify_failure.assert_called_once()
        call_kwargs = slack_mock.notify_failure.call_args
        assert call_kwargs.kwargs["error_code"] == "470"

    @pytest.mark.asyncio
    async def test_failed_status_no_slack_configured(
        self, app_no_slack, store: MessageStatusStore
    ) -> None:
        store.register_message("msg-100", "send_text_message", "s1", "5511999")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_no_slack), base_url="http://test"
        ) as client:
            resp = await client.post("/webhook/status", json=_valid_payload(status="failed"))

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_non_failed_status_no_slack(
        self, app, store: MessageStatusStore, slack_mock: SlackNotifier
    ) -> None:
        store.register_message("msg-100", "send_text_message", "s1", "5511999")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/webhook/status", json=_valid_payload(status="delivered"))

        await asyncio.sleep(0)
        slack_mock.notify_failure.assert_not_called()

    @pytest.mark.asyncio
    async def test_audit_logged(self, app, store: MessageStatusStore, audit: AuditLogger) -> None:
        store.register_message("msg-100", "send_text_message", "s1", "5511999")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/webhook/status", json=_valid_payload())

        entries = audit.get_all_entries()
        webhook_entries = [e for e in entries if e.action == "webhook_status_update"]
        assert len(webhook_entries) == 1
        assert webhook_entries[0].params["message_id"] == "msg-100"
        assert webhook_entries[0].params["status"] == "delivered"


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health(self, app, store: MessageStatusStore) -> None:
        store.register_message("msg-1", "send_text_message", "s1", "5511999")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["tracked_messages"] == 1
