"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from wati_agent.api.mock import MockWatiClient
from wati_agent.config import Settings
from wati_agent.observability.audit import AuditLogger


@pytest.fixture
def settings() -> Settings:
    return Settings(
        use_mock_api=True,
        wati_api_token="test-token",
        llm_model="anthropic/claude-sonnet-4-20250514",
        anthropic_api_key="test-key",
        dry_run_default=True,
        log_level="DEBUG",
    )


@pytest.fixture
def client() -> MockWatiClient:
    return MockWatiClient()


@pytest.fixture
def audit(tmp_path: Path) -> AuditLogger:
    """AuditLogger backed by a temp file (no cross-test pollution)."""
    return AuditLogger(audit_file=tmp_path / "audit.jsonl")
