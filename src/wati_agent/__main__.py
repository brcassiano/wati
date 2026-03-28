"""Entry point: python -m wati_agent"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from wati_agent.agent.agent import WatiAgent
from wati_agent.api import create_api_client
from wati_agent.cli.chat import chat_loop
from wati_agent.config import Settings
from wati_agent.observability.audit import AuditLogger
from wati_agent.observability.logging import setup_logging


async def async_main() -> None:
    """Initialize dependencies and start the CLI."""
    settings = Settings()
    setup_logging(settings.log_level)

    api_client, is_mock_fallback, api_version = await create_api_client(settings)
    api_mode = "mock" if (settings.use_mock_api or is_mock_fallback) else "real"
    audit = AuditLogger(api_mode=api_mode)
    agent = WatiAgent(settings, api_client, audit)

    await chat_loop(
        agent,
        settings,
        audit,
        is_mock_fallback=is_mock_fallback,
        api_version=api_version,
    )


def main() -> None:
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)

    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass

    # Suppress SSL transport cleanup errors that print to stderr after
    # the event loop closes. This is a known Python 3.10 issue with
    # aiohttp/httpx connections open at shutdown — harmless but noisy.
    # We redirect stderr to /dev/null before the interpreter exits and
    # the garbage collector tries to close SSL sockets.
    try:
        sys.stderr.close()
        sys.stderr = open(os.devnull, "w")  # noqa: SIM115
    except Exception:
        pass


if __name__ == "__main__":
    main()
