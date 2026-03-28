"""Conversational memory: per-session message history.

Sessions are saved individually to data/sessions/{session_id}.json.
On startup, ALL previous sessions are loaded as accumulated context.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SESSIONS_BASE = Path("data/sessions")

# Max messages to include in context preload (prevents token overflow)
MAX_CONTEXT_MESSAGES = 60
# Max chars per message in context preload
MAX_MESSAGE_LENGTH = 600


class ConversationMemory:
    """In-memory session store. Keeps last N message pairs per session.

    Sessions are isolated by api_mode (mock/real) so mock and real
    conversations never contaminate each other's context.
    """

    def __init__(self, max_turns: int = 20, api_mode: str = "real") -> None:
        self._sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._max_turns = max_turns
        self.sessions_dir = SESSIONS_BASE / api_mode

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Get message history for a session (copy)."""
        return list(self._sessions[session_id])

    def add_message(self, session_id: str, role: str, content: Any) -> None:
        """Append a message to session history."""
        self._sessions[session_id].append({"role": role, "content": content})
        self._trim(session_id)

    def set_messages(self, session_id: str, messages: list[dict[str, Any]]) -> None:
        """Replace session history (used after full agent loop)."""
        self._sessions[session_id] = messages
        self._trim(session_id)

    def clear(self, session_id: str) -> None:
        """Clear session history."""
        self._sessions.pop(session_id, None)

    def save_session(self, session_id: str) -> None:
        """Save session to its own file + update index."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        messages = self._sessions.get(session_id, [])
        # Filter only user and assistant text messages
        saveable = []
        for m in messages:
            if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
                saveable.append({"role": m["role"], "content": m["content"]})

        if not saveable:
            return  # don't save empty sessions

        data = {
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message_count": len(saveable),
            "messages": saveable,
        }

        # Save individual session file
        path = self.sessions_dir / f"{session_id}.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def load_all_previous_sessions(self) -> list[dict]:
        """Load ALL previous sessions from disk, sorted oldest first.

        Returns list of session dicts, each with session_id and messages.
        """
        if not self.sessions_dir.exists():
            return []

        sessions: list[dict] = []
        for path in self.sessions_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                if data.get("messages"):
                    sessions.append(data)
            except (json.JSONDecodeError, OSError):
                continue

        # Sort by file modification time (oldest first)
        sessions.sort(
            key=lambda s: (
                (self.sessions_dir / f"{s['session_id']}.json").stat().st_mtime
                if (self.sessions_dir / f"{s['session_id']}.json").exists()
                else 0
            )
        )
        return sessions

    def preload_context(self, session_id: str, previous_sessions: list[dict]) -> None:
        """Preload accumulated context from ALL previous sessions.

        Takes the most recent messages (up to MAX_CONTEXT_MESSAGES) across
        all sessions and injects them as historical context for the LLM.
        """
        if not previous_sessions:
            return

        lines = [
            "[Previous conversation history — "
            "the user had these conversations in prior sessions. "
            "Use this to answer questions about past actions.]\n"
        ]

        # Include messages grouped by session with separators and dates
        total_messages = 0
        for session in previous_sessions:
            session_msgs = session.get("messages", [])
            if not session_msgs:
                continue
            ts = session.get("timestamp", "")
            date_label = ""
            if ts:
                try:
                    dt = datetime.fromisoformat(ts)
                    date_label = f" ({dt.strftime('%Y-%m-%d %H:%M UTC')})"
                except ValueError:
                    pass
            lines.append(f"\n--- Session {session.get('session_id', '?')[:8]}{date_label} ---")
            for m in session_msgs:
                if total_messages >= MAX_CONTEXT_MESSAGES:
                    break
                role = "User" if m.get("role") == "user" else "Assistant"
                content = m.get("content", "")
                if len(content) > MAX_MESSAGE_LENGTH:
                    content = content[: MAX_MESSAGE_LENGTH - 3] + "..."
                lines.append(f"{role}: {content}")
                total_messages += 1

        context_msg = {
            "role": "user",
            "content": "\n".join(lines)
            + "\n\n[End of previous sessions. New session starts now. "
            + "Use the above as context if the user references past actions.]",
        }
        ack_msg = {
            "role": "assistant",
            "content": "Understood. I have the context from all previous "
            "sessions and will use it to answer any questions about past "
            "actions.",
        }
        self._sessions[session_id] = [context_msg, ack_msg]

    def _trim(self, session_id: str) -> None:
        """Keep only the last max_turns * 2 messages."""
        max_messages = self._max_turns * 2
        messages = self._sessions[session_id]
        if len(messages) > max_messages:
            self._sessions[session_id] = messages[-max_messages:]
