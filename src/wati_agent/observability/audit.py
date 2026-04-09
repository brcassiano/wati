"""Audit trail for all API actions taken by the agent.

Persists to data/audit.jsonl (append-only). Each line is a JSON entry.
In-memory list for fast access during current session.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, Field

AUDIT_BASE = Path("data/audit")


def audit_file_for_mode(api_mode: str) -> Path:
    """Return the JSONL audit file path for a given API mode."""
    return AUDIT_BASE / f"{api_mode}.jsonl"


class AuditEntry(BaseModel):
    """Single audit log entry."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: str
    action: str
    method: str = ""
    endpoint: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    success: bool = True
    status_code: int | None = None
    duration_ms: float | None = None
    error: str | None = None
    dry_run: bool = False
    plan_id: str | None = None
    step_id: str | None = None


class AuditLogger:
    """Append-only structured log of all API actions.

    Keeps entries in-memory for fast access and persists each entry
    to a JSONL file for cross-session history.
    """

    def __init__(self, api_mode: str = "real", audit_file: Path | None = None) -> None:
        self._log = structlog.get_logger("audit")
        self._entries: list[AuditEntry] = []
        self._file = audit_file or audit_file_for_mode(api_mode)
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._listeners: list[Callable[[AuditEntry], None]] = []

    def add_listener(self, callback: Callable[[AuditEntry], None]) -> None:
        """Register a callback invoked after each new entry is logged."""
        self._listeners.append(callback)

    def log_action(
        self,
        session_id: str,
        action: str,
        method: str = "",
        endpoint: str = "",
        params: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        success: bool = True,
        status_code: int | None = None,
        duration_ms: float | None = None,
        error: str | None = None,
        dry_run: bool = False,
        plan_id: str | None = None,
        step_id: str | None = None,
    ) -> AuditEntry:
        """Record an API action and return the entry."""
        entry = AuditEntry(
            session_id=session_id,
            action=action,
            method=method,
            endpoint=endpoint,
            params=params or {},
            result=result,
            success=success,
            status_code=status_code,
            duration_ms=duration_ms,
            error=error,
            dry_run=dry_run,
            plan_id=plan_id,
            step_id=step_id,
        )
        self._entries.append(entry)
        self._persist(entry)
        for listener in self._listeners:
            listener(entry)
        self._log.info(
            "api_action",
            session_id=session_id,
            action=action,
            method=method,
            endpoint=endpoint,
            success=success,
            duration_ms=duration_ms,
        )
        return entry

    def _persist(self, entry: AuditEntry) -> None:
        """Append entry to JSONL file."""
        try:
            with open(self._file, "a", encoding="utf-8") as f:
                f.write(entry.model_dump_json() + "\n")
        except OSError:
            self._log.warning("audit_persist_failed", file=str(self._file))

    def get_session_entries(self, session_id: str) -> list[AuditEntry]:
        """Get all audit entries for a session (in-memory, current session)."""
        return [e for e in self._entries if e.session_id == session_id]

    def get_all_entries(self) -> list[AuditEntry]:
        """Get all in-memory audit entries."""
        return list(self._entries)

    def load_all_from_disk(self) -> list[AuditEntry]:
        """Load ALL audit entries from the JSONL file (cross-session)."""
        if not self._file.exists():
            return []
        entries: list[AuditEntry] = []
        with open(self._file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(AuditEntry.model_validate_json(line))
                    except Exception:
                        continue  # skip malformed lines
        return entries

    def load_session_from_disk(self, session_id: str) -> list[AuditEntry]:
        """Load entries for a specific session from disk."""
        return [e for e in self.load_all_from_disk() if e.session_id == session_id]

    def list_sessions_from_disk(self) -> list[dict[str, Any]]:
        """List all sessions found in disk audit log with summary info."""
        all_entries = self.load_all_from_disk()
        sessions: dict[str, dict[str, Any]] = {}
        for e in all_entries:
            if e.session_id not in sessions:
                sessions[e.session_id] = {
                    "session_id": e.session_id,
                    "first_action": e.timestamp,
                    "last_action": e.timestamp,
                    "action_count": 0,
                }
            s = sessions[e.session_id]
            s["action_count"] += 1
            if e.timestamp > s["last_action"]:
                s["last_action"] = e.timestamp
        return sorted(sessions.values(), key=lambda s: s["last_action"], reverse=True)
