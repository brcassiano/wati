"""Tests for AuditLogger — in-memory + JSONL persistence."""

from __future__ import annotations

from pathlib import Path

from wati_agent.observability.audit import AuditLogger

# --- In-memory ---


def test_log_action_returns_entry(audit: AuditLogger) -> None:
    entry = audit.log_action(session_id="s1", action="get_contacts")
    assert entry.session_id == "s1"
    assert entry.action == "get_contacts"
    assert entry.success is True


def test_get_session_entries_filters(audit: AuditLogger) -> None:
    audit.log_action(session_id="s1", action="a")
    audit.log_action(session_id="s2", action="b")
    audit.log_action(session_id="s1", action="c")

    s1 = audit.get_session_entries("s1")
    assert len(s1) == 2
    assert all(e.session_id == "s1" for e in s1)


def test_get_all_entries(audit: AuditLogger) -> None:
    audit.log_action(session_id="s1", action="a")
    audit.log_action(session_id="s2", action="b")
    assert len(audit.get_all_entries()) == 2


# --- JSONL persistence ---


def test_persist_creates_file(audit: AuditLogger) -> None:
    audit.log_action(session_id="s1", action="test")
    assert audit._file.exists()


def test_persist_appends_lines(audit: AuditLogger) -> None:
    audit.log_action(session_id="s1", action="a")
    audit.log_action(session_id="s1", action="b")
    audit.log_action(session_id="s2", action="c")

    lines = audit._file.read_text().strip().split("\n")
    assert len(lines) == 3


def test_load_all_from_disk(audit: AuditLogger) -> None:
    audit.log_action(session_id="s1", action="a", method="GET")
    audit.log_action(session_id="s2", action="b", method="POST")

    # New logger instance reading the same file
    fresh = AuditLogger(audit_file=audit._file)
    entries = fresh.load_all_from_disk()
    assert len(entries) == 2
    assert entries[0].action == "a"
    assert entries[1].method == "POST"


def test_load_session_from_disk(audit: AuditLogger) -> None:
    audit.log_action(session_id="s1", action="a")
    audit.log_action(session_id="s2", action="b")
    audit.log_action(session_id="s1", action="c")

    fresh = AuditLogger(audit_file=audit._file)
    s1 = fresh.load_session_from_disk("s1")
    assert len(s1) == 2
    assert all(e.session_id == "s1" for e in s1)


def test_list_sessions_from_disk(audit: AuditLogger) -> None:
    audit.log_action(session_id="s1", action="a")
    audit.log_action(session_id="s1", action="b")
    audit.log_action(session_id="s2", action="c")

    fresh = AuditLogger(audit_file=audit._file)
    sessions = fresh.list_sessions_from_disk()
    assert len(sessions) == 2
    # Sessions sorted by last_action desc
    ids = [s["session_id"] for s in sessions]
    assert "s1" in ids
    assert "s2" in ids
    # Check action counts
    s1_info = next(s for s in sessions if s["session_id"] == "s1")
    assert s1_info["action_count"] == 2


def test_load_from_empty_file(tmp_path: Path) -> None:
    audit = AuditLogger(audit_file=tmp_path / "empty.jsonl")
    assert audit.load_all_from_disk() == []


def test_load_skips_malformed_lines(audit: AuditLogger) -> None:
    audit.log_action(session_id="s1", action="valid")
    # Manually append bad line
    with open(audit._file, "a") as f:
        f.write("this is not json\n")
    audit.log_action(session_id="s1", action="also_valid")

    fresh = AuditLogger(audit_file=audit._file)
    entries = fresh.load_all_from_disk()
    assert len(entries) == 2  # malformed line skipped


def test_audit_entry_all_fields_persist(audit: AuditLogger) -> None:
    audit.log_action(
        session_id="s1",
        action="send_template_message",
        method="POST",
        endpoint="/messageTemplates/send",
        params={"target": "5511999", "template_id": "abc"},
        result={"ok": True},
        success=True,
        duration_ms=42.5,
        plan_id="plan-1",
        step_id="step-1",
    )

    fresh = AuditLogger(audit_file=audit._file)
    entries = fresh.load_all_from_disk()
    e = entries[0]
    assert e.method == "POST"
    assert e.endpoint == "/messageTemplates/send"
    assert e.params["target"] == "5511999"
    assert e.result == {"ok": True}
    assert e.duration_ms == 42.5
    assert e.plan_id == "plan-1"
    assert e.step_id == "step-1"
