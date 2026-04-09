"""Tests for MessageStatusStore."""

from __future__ import annotations

from pathlib import Path

import pytest

from wati_agent.observability.audit import AuditLogger
from wati_agent.webhook.status_store import MessageStatusStore, _extract_message_id


@pytest.fixture
def audit(tmp_path: Path) -> AuditLogger:
    return AuditLogger(audit_file=tmp_path / "audit.jsonl")


@pytest.fixture
def store(audit: AuditLogger, tmp_path: Path) -> MessageStatusStore:
    return MessageStatusStore(audit=audit, persist_path=tmp_path / "status.jsonl")


class TestExtractMessageId:
    def test_send_text_message(self) -> None:
        assert _extract_message_id("send_text_message", {"id": "msg-1"}) == "msg-1"

    def test_send_template_message(self) -> None:
        assert _extract_message_id("send_template_message", {"message_id": "msg-2"}) == "msg-2"

    def test_unknown_action(self) -> None:
        assert _extract_message_id("get_contacts", {"id": "x"}) is None

    def test_none_result(self) -> None:
        assert _extract_message_id("send_text_message", None) is None

    def test_missing_key(self) -> None:
        assert _extract_message_id("send_text_message", {"other": "val"}) is None


class TestIndexFromAudit:
    def test_indexes_send_text(self, store: MessageStatusStore, audit: AuditLogger) -> None:
        audit.log_action(
            session_id="s1",
            action="send_text_message",
            params={"target": "5511999"},
            result={"id": "msg-100"},
            success=True,
        )
        store.index_from_audit()
        record = store.get("msg-100")
        assert record is not None
        assert record.target == "5511999"
        assert record.original_action == "send_text_message"

    def test_indexes_send_template(self, store: MessageStatusStore, audit: AuditLogger) -> None:
        audit.log_action(
            session_id="s2",
            action="send_template_message",
            params={"target": "5511888"},
            result={"message_id": "msg-200", "result": True},
            success=True,
        )
        store.index_from_audit()
        record = store.get("msg-200")
        assert record is not None
        assert record.target == "5511888"

    def test_skips_failed_entries(self, store: MessageStatusStore, audit: AuditLogger) -> None:
        audit.log_action(
            session_id="s3",
            action="send_text_message",
            params={"target": "5511777"},
            result=None,
            success=False,
            error="API error",
        )
        store.index_from_audit()
        assert store.count == 0

    def test_skips_non_message_tools(self, store: MessageStatusStore, audit: AuditLogger) -> None:
        audit.log_action(
            session_id="s4",
            action="get_contacts",
            params={},
            result={"contacts": []},
            success=True,
        )
        store.index_from_audit()
        assert store.count == 0


class TestUpdateStatus:
    def test_update_known_message(self, store: MessageStatusStore) -> None:
        store.register_message("msg-1", "send_text_message", "s1", "5511999")
        record = store.update_status("msg-1", "delivered")
        assert record is not None
        assert record.current_status == "delivered"
        assert len(record.status_history) == 2  # sent + delivered

    def test_update_unknown_message(self, store: MessageStatusStore) -> None:
        assert store.update_status("nonexistent", "delivered") is None

    def test_status_history_order(self, store: MessageStatusStore) -> None:
        store.register_message("msg-2", "send_text_message", "s1", "5511999")
        store.update_status("msg-2", "delivered")
        store.update_status("msg-2", "read")
        record = store.get("msg-2")
        assert record is not None
        statuses = [s for s, _ in record.status_history]
        assert statuses == ["sent", "delivered", "read"]


class TestDuplicateDetection:
    def test_not_duplicate_initially(self, store: MessageStatusStore) -> None:
        assert not store.is_duplicate("msg-1", "delivered")

    def test_duplicate_after_update(self, store: MessageStatusStore) -> None:
        store.register_message("msg-1", "send_text_message", "s1", "5511999")
        store.update_status("msg-1", "delivered")
        assert store.is_duplicate("msg-1", "delivered")

    def test_different_status_not_duplicate(self, store: MessageStatusStore) -> None:
        store.register_message("msg-1", "send_text_message", "s1", "5511999")
        store.update_status("msg-1", "delivered")
        assert not store.is_duplicate("msg-1", "read")


class TestPersistence:
    def test_persists_updates(self, store: MessageStatusStore, tmp_path: Path) -> None:
        store.register_message("msg-1", "send_text_message", "s1", "5511999")
        store.update_status("msg-1", "delivered")
        store.update_status("msg-1", "read")

        status_file = tmp_path / "status.jsonl"
        assert status_file.exists()
        lines = status_file.read_text().strip().split("\n")
        assert len(lines) == 2  # delivered + read (initial "sent" not persisted)


class TestRegisterMessage:
    def test_register_and_get(self, store: MessageStatusStore) -> None:
        record = store.register_message("msg-new", "send_text_message", "s1", "5511999")
        assert record.message_id == "msg-new"
        assert record.current_status == "sent"
        assert store.count == 1

    def test_register_duplicate_overwrites(self, store: MessageStatusStore) -> None:
        store.register_message("msg-1", "send_text_message", "s1", "5511999")
        store.register_message("msg-1", "send_text_message", "s2", "5511888")
        record = store.get("msg-1")
        assert record is not None
        assert record.session_id == "s2"  # overwritten
