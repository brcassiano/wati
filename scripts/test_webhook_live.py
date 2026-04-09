"""Live test: starts webhook server with a pre-registered message for manual curl testing."""

import asyncio
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from wati_agent.config import Settings
from wati_agent.observability.audit import AuditLogger
from wati_agent.webhook.app import create_webhook_app
from wati_agent.webhook.slack import SlackNotifier
from wati_agent.webhook.status_store import MessageStatusStore

TEST_MESSAGE_ID = "test-msg-001"
TEST_TARGET = "+5511999999999"


async def main() -> None:
    settings = Settings()
    audit = AuditLogger(api_mode="mock", audit_file=Path("/tmp/webhook_test_audit.jsonl"))

    store = MessageStatusStore(audit=audit, persist_path=Path("/tmp/webhook_test_status.jsonl"))
    store.register_message(
        message_id=TEST_MESSAGE_ID,
        action="send_text_message",
        session_id="test-session",
        target=TEST_TARGET,
    )
    print(f"\n  Registered test message: {TEST_MESSAGE_ID} -> {TEST_TARGET}")
    print(f"  Tracked messages: {store.count}")

    slack = SlackNotifier(settings.slack_webhook_url) if settings.slack_webhook_url else None
    if slack:
        print(f"  Slack configured: yes")
    else:
        print(f"  Slack configured: no (SLACK_WEBHOOK_URL not set)")

    app = create_webhook_app(
        status_store=store,
        slack=slack,
        audit=audit,
        webhook_path=settings.webhook_path,
    )

    port = settings.webhook_port
    print(f"\n  Webhook server running on http://localhost:{port}")
    print(f"  Health:    curl http://localhost:{port}/health")
    print(f"  Deliver:   curl -X POST http://localhost:{port}/webhook/status -H 'Content-Type: application/json' -d '{{\"event_type\":\"message_status\",\"message_id\":\"{TEST_MESSAGE_ID}\",\"status\":\"delivered\"}}'")
    print(f"  Fail:      curl -X POST http://localhost:{port}/webhook/status -H 'Content-Type: application/json' -d '{{\"event_type\":\"message_status\",\"message_id\":\"{TEST_MESSAGE_ID}\",\"status\":\"failed\",\"error_code\":\"470\",\"error_message\":\"Message undeliverable\"}}'")
    print()

    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)

    try:
        await server.serve()
    finally:
        if slack:
            await slack.close()


if __name__ == "__main__":
    asyncio.run(main())
