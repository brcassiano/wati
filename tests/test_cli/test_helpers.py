"""Tests for CLI helper functions."""

from __future__ import annotations

from wati_agent.cli.chat import _is_negative

# --- _is_negative ---


def test_negative_words_cancel() -> None:
    assert _is_negative("no") is True
    assert _is_negative("n") is True
    assert _is_negative("nao") is True
    assert _is_negative("não") is True
    assert _is_negative("cancel") is True
    assert _is_negative("cancelar") is True
    assert _is_negative("stop") is True
    assert _is_negative("para") is True
    assert _is_negative("abort") is True
    assert _is_negative("esquece") is True
    assert _is_negative("forget") is True
    assert _is_negative("nope") is True
    assert _is_negative("negative") is True


def test_positive_words_confirm() -> None:
    assert _is_negative("y") is False
    assert _is_negative("yes") is False
    assert _is_negative("sim") is False
    assert _is_negative("ok") is False
    assert _is_negative("sure") is False
    assert _is_negative("bora") is False
    assert _is_negative("manda") is False
    assert _is_negative("let's go") is False
    assert _is_negative("go ahead") is False
    assert _is_negative("do it") is False
    assert _is_negative("claro") is False
    assert _is_negative("pode ser") is False
    assert _is_negative("vai") is False
    assert _is_negative("") is False


def test_empty_string_is_positive() -> None:
    """Empty input (just pressing Enter) should confirm."""
    assert _is_negative("") is False
    assert _is_negative("  ") is False


def test_case_insensitive() -> None:
    assert _is_negative("NO") is True
    assert _is_negative("Cancel") is True
    assert _is_negative("STOP") is True
