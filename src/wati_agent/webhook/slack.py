"""Slack notification for failed message deliveries."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import structlog

if TYPE_CHECKING:
    from wati_agent.webhook.status_store import MessageStatusRecord

logger = structlog.get_logger(__name__)


class SlackNotifier:
    """Sends Slack notifications via incoming webhook URL.

    Fire-and-forget: all errors are logged but never propagated.
    """

    def __init__(self, webhook_url: str, http_client: httpx.AsyncClient | None = None) -> None:
        self._url = webhook_url
        self._client = http_client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = http_client is None

    async def notify_failure(
        self,
        record: MessageStatusRecord,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Send a Slack notification for a failed message. Returns True on success."""
        error_detail = ""
        if error_code:
            error_detail += f"Code: `{error_code}`"
        if error_message:
            error_detail += f"\n{error_message}" if error_detail else error_message

        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "Message Delivery Failed",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Message ID:*\n`{record.message_id}`"},
                        {"type": "mrkdwn", "text": f"*Target:*\n{record.target}"},
                        {"type": "mrkdwn", "text": f"*Action:*\n{record.original_action}"},
                        {"type": "mrkdwn", "text": f"*Session:*\n`{record.session_id[:8]}...`"},
                    ],
                },
            ],
        }

        if error_detail:
            payload["blocks"].append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Error:*\n{error_detail}"},
                }
            )

        try:
            resp = await self._client.post(self._url, json=payload)
            resp.raise_for_status()
            logger.info("slack_notification_sent", message_id=record.message_id)
            return True
        except Exception as exc:
            logger.error(
                "slack_notification_failed",
                message_id=record.message_id,
                error=str(exc),
            )
            return False

    async def close(self) -> None:
        """Close the HTTP client if we own it."""
        if self._owns_client:
            await self._client.aclose()
