"""Webhook server for receiving WATI status callbacks."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import uvicorn

from wati_agent.webhook.app import create_webhook_app
from wati_agent.webhook.slack import SlackNotifier
from wati_agent.webhook.status_store import MessageStatusStore

if TYPE_CHECKING:
    from wati_agent.config import Settings
    from wati_agent.observability.audit import AuditLogger

__all__ = ["start_webhook_server"]


async def start_webhook_server(settings: Settings, audit: AuditLogger) -> None:
    """Start the webhook HTTP server (runs until cancelled)."""
    status_store = MessageStatusStore(audit=audit)
    status_store.index_from_audit()

    slack = SlackNotifier(settings.slack_webhook_url) if settings.slack_webhook_url else None

    app = create_webhook_app(
        status_store=status_store,
        slack=slack,
        audit=audit,
        webhook_path=settings.webhook_path,
    )

    config = uvicorn.Config(
        app,
        host=settings.webhook_host,
        port=settings.webhook_port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    try:
        await server.serve()
    except asyncio.CancelledError:
        # Suppress uvicorn shutdown noise (CancelledError tracebacks)
        for name in ("uvicorn.error", "uvicorn", "uvicorn.access"):
            logging.getLogger(name).setLevel(logging.CRITICAL)
        server.should_exit = True
    finally:
        if slack:
            await slack.close()
