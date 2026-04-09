"""Starlette webhook application — receives WATI status callbacks."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import structlog
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from wati_agent.webhook.models import MessageStatus, WebhookStatusPayload

if TYPE_CHECKING:
    from wati_agent.observability.audit import AuditLogger
    from wati_agent.webhook.slack import SlackNotifier
    from wati_agent.webhook.status_store import MessageStatusStore

logger = structlog.get_logger(__name__)


async def handle_status_webhook(request: Request) -> JSONResponse:
    """Process an incoming message status webhook from WATI.

    Always returns 200 to prevent WATI from retrying.
    Errors are handled internally and logged.
    """
    store: MessageStatusStore = request.app.state.status_store
    slack: SlackNotifier | None = request.app.state.slack
    audit: AuditLogger = request.app.state.audit

    # 1. Parse JSON body
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        logger.warning("webhook_invalid_json")
        return JSONResponse({"ok": False, "error": "invalid json"})

    # 2. Validate payload
    try:
        payload = WebhookStatusPayload.model_validate(body)
    except ValidationError as exc:
        errors = exc.error_count()
        logger.warning("webhook_invalid_payload", error_count=errors)
        msg = f"invalid payload: {errors} validation error(s)"
        return JSONResponse({"ok": False, "error": msg})

    # 3. Check duplicate
    if store.is_duplicate(payload.message_id, payload.status.value):
        logger.debug(
            "webhook_duplicate", message_id=payload.message_id, status=payload.status.value
        )
        return JSONResponse({"ok": True, "message": "duplicate"})

    # 4. Look up message
    record = store.get(payload.message_id)
    if record is None:
        logger.warning("webhook_unknown_message", message_id=payload.message_id)
        return JSONResponse({"ok": True, "message": "unknown message_id"})

    # 5. Capture previous status before mutation, then update
    previous_status = record.current_status
    store.update_status(
        message_id=payload.message_id,
        status=payload.status.value,
        timestamp=payload.timestamp,
    )

    # 6. Slack notification on failure (fire-and-forget)
    if payload.status == MessageStatus.failed and slack is not None:
        asyncio.create_task(
            slack.notify_failure(
                record=record,
                error_code=payload.error_code,
                error_message=payload.error_message,
            )
        )

    # 7. Audit log
    audit.log_action(
        session_id=record.session_id,
        action="webhook_status_update",
        method="POST",
        endpoint=str(request.url.path),
        params={
            "message_id": payload.message_id,
            "status": payload.status.value,
            "event_type": payload.event_type,
        },
        result={"previous_status": previous_status, "new_status": payload.status.value},
        success=True,
    )

    return JSONResponse({"ok": True, "message": "accepted"})


async def health(request: Request) -> JSONResponse:
    """Health check endpoint."""
    store: MessageStatusStore = request.app.state.status_store
    return JSONResponse({"ok": True, "tracked_messages": store.count})


def create_webhook_app(
    status_store: MessageStatusStore,
    slack: SlackNotifier | None,
    audit: AuditLogger,
    webhook_path: str = "/webhook/status",
) -> Starlette:
    """Create and configure the Starlette webhook application."""
    routes = [
        Route(webhook_path, handle_status_webhook, methods=["POST"]),
        Route("/health", health, methods=["GET"]),
    ]

    app = Starlette(routes=routes)
    app.state.status_store = status_store
    app.state.slack = slack
    app.state.audit = audit

    return app
