"""Structured logging configuration using structlog."""

from __future__ import annotations

import logging

import structlog


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structlog with JSON output (production) or console (debug).

    In CLI mode, logs are suppressed from stdout — they go to the audit trail
    only. Users see clean chat output; logs are accessible via /audit command.
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    is_debug = numeric_level <= logging.DEBUG

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if is_debug:
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    # In non-debug mode, suppress structlog output to keep CLI clean.
    # Audit entries are still recorded in-memory via AuditLogger.
    if is_debug:
        logger_factory = structlog.PrintLoggerFactory()
    else:
        logger_factory = structlog.PrintLoggerFactory(file=open("/dev/null", "w"))  # noqa: SIM115

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=logger_factory,
        cache_logger_on_first_use=True,
    )

    # Silence third-party loggers (litellm, httpx, etc.)
    logging.basicConfig(format="%(message)s", level=logging.WARNING)
    for noisy_logger in ("LiteLLM", "litellm", "httpx", "httpcore", "openai"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
