"""Tests for ConversationMemory — in-memory + persistence."""

from __future__ import annotations

import json
from pathlib import Path

from wati_agent.agent.memory import ConversationMemory

# --- In-memory operations ---


def test_get_messages_empty() -> None:
    mem = ConversationMemory()
    assert mem.get_messages("session1") == []


def test_add_message() -> None:
    mem = ConversationMemory()
    mem.add_message("s1", "user", "hello")
    mem.add_message("s1", "assistant", "hi there")
    messages = mem.get_messages("s1")
    assert len(messages) == 2
    assert messages[0] == {"role": "user", "content": "hello"}


def test_set_messages_replaces() -> None:
    mem = ConversationMemory()
    mem.add_message("s1", "user", "old")
    mem.set_messages("s1", [{"role": "user", "content": "new"}])
    assert len(mem.get_messages("s1")) == 1
    assert mem.get_messages("s1")[0]["content"] == "new"


def test_clear() -> None:
    mem = ConversationMemory()
    mem.add_message("s1", "user", "hello")
    mem.clear("s1")
    assert mem.get_messages("s1") == []


def test_get_messages_returns_copy() -> None:
    mem = ConversationMemory()
    mem.add_message("s1", "user", "hello")
    copy = mem.get_messages("s1")
    copy.append({"role": "fake"})
    assert len(mem.get_messages("s1")) == 1  # unchanged


def test_sessions_are_isolated() -> None:
    mem = ConversationMemory()
    mem.add_message("s1", "user", "hello")
    mem.add_message("s2", "user", "different")
    assert len(mem.get_messages("s1")) == 1
    assert len(mem.get_messages("s2")) == 1


# --- Trimming ---


def test_trim_respects_max_turns() -> None:
    mem = ConversationMemory(max_turns=2)
    for i in range(10):
        mem.add_message("s1", "user", f"msg {i}")
    # max_turns=2 means max 4 messages
    assert len(mem.get_messages("s1")) == 4


# --- Persistence ---


def test_save_session_creates_individual_file(tmp_path: Path) -> None:
    mem = ConversationMemory()
    mem.add_message("s1", "user", "hello")
    mem.add_message("s1", "assistant", "hi")
    # Tool messages should be filtered out
    mem.add_message("s1", "tool", {"result": "data"})

    mem.sessions_dir = tmp_path
    mem.save_session("s1")
    data = json.loads((tmp_path / "s1.json").read_text())

    assert data["session_id"] == "s1"
    assert data["message_count"] == 2  # tool msg filtered
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"


def test_save_empty_session_does_nothing(tmp_path: Path) -> None:
    mem = ConversationMemory()
    mem.sessions_dir = tmp_path
    mem.save_session("empty")
    assert not (tmp_path / "empty.json").exists()


def test_load_all_previous_sessions(tmp_path: Path) -> None:
    # Create two session files
    s1 = {
        "session_id": "s1",
        "message_count": 1,
        "messages": [{"role": "user", "content": "session 1"}],
    }
    s2 = {
        "session_id": "s2",
        "message_count": 1,
        "messages": [{"role": "user", "content": "session 2"}],
    }
    (tmp_path / "s1.json").write_text(json.dumps(s1))
    (tmp_path / "s2.json").write_text(json.dumps(s2))

    mem = ConversationMemory()
    mem.sessions_dir = tmp_path
    sessions = mem.load_all_previous_sessions()

    assert len(sessions) == 2
    contents = [s["messages"][0]["content"] for s in sessions]
    assert "session 1" in contents
    assert "session 2" in contents


def test_load_previous_sessions_empty_dir(tmp_path: Path) -> None:
    mem = ConversationMemory()
    mem.sessions_dir = tmp_path
    assert mem.load_all_previous_sessions() == []


def test_load_previous_sessions_skips_corrupted(tmp_path: Path) -> None:
    s1 = {"session_id": "s1", "message_count": 1, "messages": [{"role": "user", "content": "ok"}]}
    (tmp_path / "s1.json").write_text(json.dumps(s1))
    (tmp_path / "bad.json").write_text("not json!")

    mem = ConversationMemory()
    mem.sessions_dir = tmp_path
    sessions = mem.load_all_previous_sessions()
    assert len(sessions) == 1


def test_load_previous_sessions_skips_empty(tmp_path: Path) -> None:
    empty = {"session_id": "e", "message_count": 0, "messages": []}
    (tmp_path / "e.json").write_text(json.dumps(empty))

    mem = ConversationMemory()
    mem.sessions_dir = tmp_path
    sessions = mem.load_all_previous_sessions()
    assert len(sessions) == 0  # empty sessions skipped


# --- Context preload (accumulated) ---


def test_preload_context_from_multiple_sessions() -> None:
    mem = ConversationMemory()
    sessions = [
        {
            "session_id": "s1",
            "messages": [
                {"role": "user", "content": "send welcome to VIPs"},
                {"role": "assistant", "content": "Done, sent to 5 VIPs."},
            ],
        },
        {
            "session_id": "s2",
            "messages": [
                {"role": "user", "content": "how many contacts?"},
                {"role": "assistant", "content": "You have 10 contacts."},
            ],
        },
    ]
    mem.preload_context("s3", sessions)
    messages = mem.get_messages("s3")
    assert len(messages) == 2  # context + ack
    content = messages[0]["content"]
    assert "send welcome to VIPs" in content
    assert "how many contacts?" in content
    assert "previous sessions" in content.lower()


def test_preload_context_empty() -> None:
    mem = ConversationMemory()
    mem.preload_context("s2", [])
    assert mem.get_messages("s2") == []


def test_preload_context_truncates_long_messages() -> None:
    mem = ConversationMemory()
    sessions = [
        {"session_id": "s1", "messages": [{"role": "user", "content": "x" * 1000}]},
    ]
    mem.preload_context("s2", sessions)
    messages = mem.get_messages("s2")
    assert "..." in messages[0]["content"]
