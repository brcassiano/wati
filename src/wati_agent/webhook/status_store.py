"""Message status tracking — correlates webhook events with sent messages."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, Field

from wati_agent.observability.audit import AuditEntry, AuditLogger

logger = structlog.get_logger(__name__)

STATUS_BASE = Path("data/message_status")

# Tools whose audit results contain a message_id
_MESSAGE_TOOLS = frozenset({"send_text_message", "send_template_message"})


class MessageStatusRecord(BaseModel):
    """Tracks the lifecycle of a single sent message."""

    message_id: str
    current_status: str = "sent"
    status_history: list[tuple[str, datetime]] = Field(default_factory=list)
    original_action: str = ""
    session_id: str = ""
    target: str = ""


def _extract_message_id(action: str, result: dict[str, Any] | None) -> str | None:
    """Extract message_id from an audit entry result dict."""
    if not result:
        return None
    if action == "send_text_message":
        return result.get("id")
    if action == "send_template_message":
        return result.get("message_id")
    return None


class MessageStatusStore:
    """In-memory index of sent messages, updated by webhook events.

    On startup, scans existing audit entries to build the message_id index.
    Status updates are persisted to a JSONL file for durability.
    """

    def __init__(
        self,
        audit: AuditLogger,
        persist_path: Path | None = None,
    ) -> None:
        self._audit = audit
        self._records: dict[str, MessageStatusRecord] = {}
        self._seen_events: set[tuple[str, str]] = set()  # (message_id, status)
        self._file = persist_path or STATUS_BASE / "status.jsonl"
        self._file.parent.mkdir(parents=True, exist_ok=True)
        # Auto-register new messages as they are sent
        audit.add_listener(self._on_audit_entry)

    def index_from_audit(self) -> None:
        """Scan audit entries and build the message_id -> record index."""
        for entry in self._audit.get_all_entries():
            if entry.action not in _MESSAGE_TOOLS or not entry.success:
                continue
            msg_id = _extract_message_id(entry.action, entry.result)
            if not msg_id:
                continue
            target = entry.params.get("target", "")
            self._records[msg_id] = MessageStatusRecord(
                message_id=msg_id,
                current_status="sent",
                status_history=[(("sent", entry.timestamp))],
                original_action=entry.action,
                session_id=entry.session_id,
                target=target,
            )
        logger.info("status_store_indexed", message_count=len(self._records))

    def is_duplicate(self, message_id: str, status: str) -> bool:
        """Check if this exact (message_id, status) pair was already processed."""
        return (message_id, status) in self._seen_events

    def get(self, message_id: str) -> MessageStatusRecord | None:
        """Look up a message by ID. Returns None if unknown."""
        return self._records.get(message_id)

    def update_status(
        self,
        message_id: str,
        status: str,
        timestamp: datetime | None = None,
    ) -> MessageStatusRecord | None:
        """Update a message's status. Returns None if message_id is unknown."""
        record = self._records.get(message_id)
        if record is None:
            return None

        ts = timestamp or datetime.now(timezone.utc)
        record.current_status = status
        record.status_history.append((status, ts))
        self._seen_events.add((message_id, status))
        self._persist_update(message_id, status, ts)

        logger.info(
            "message_status_updated",
            message_id=message_id,
            status=status,
            target=record.target,
        )
        return record

    def register_message(
        self,
        message_id: str,
        action: str,
        session_id: str,
        target: str,
        timestamp: datetime | None = None,
    ) -> MessageStatusRecord:
        """Register a newly sent message for tracking."""
        ts = timestamp or datetime.now(timezone.utc)
        record = MessageStatusRecord(
            message_id=message_id,
            current_status="sent",
            status_history=[("sent", ts)],
            original_action=action,
            session_id=session_id,
            target=target,
        )
        self._records[message_id] = record
        return record

    @property
    def count(self) -> int:
        """Number of tracked messages."""
        return len(self._records)

    def _on_audit_entry(self, entry: AuditEntry) -> None:
        """Callback from AuditLogger — auto-register newly sent messages."""
        if entry.action not in _MESSAGE_TOOLS or not entry.success:
            return
        msg_id = _extract_message_id(entry.action, entry.result)
        if not msg_id or msg_id in self._records:
            return
        target = entry.params.get("target", "")
        self.register_message(msg_id, entry.action, entry.session_id, target, entry.timestamp)
        logger.info("message_auto_registered", message_id=msg_id, target=target)

    def _persist_update(self, message_id: str, status: str, timestamp: datetime) -> None:
        """Append status update to JSONL file."""
        import json

        entry = {
            "message_id": message_id,
            "status": status,
            "timestamp": timestamp.isoformat(),
        }
        try:
            with open(self._file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            logger.warning("status_persist_failed", file=str(self._file))
