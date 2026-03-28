"""WATI API client layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from wati_agent.api.base import WatiClient
    from wati_agent.config import Settings

logger = structlog.get_logger(__name__)

HEALTH_CHECK_TIMEOUT = 5.0  # seconds


async def create_api_client(
    settings: Settings,
) -> tuple[WatiClient, bool, str]:
    """Factory: returns (client, is_mock_fallback, api_version).

    If use_mock_api is set, returns mock directly.
    Otherwise tries the real API:
      1. Try V1 health check (get_contacts)
      2. If V1 fails, fall back to mock
    """
    if settings.use_mock_api:
        from wati_agent.api.mock import MockWatiClient

        return MockWatiClient(), False, "mock"

    # Try V1
    from wati_agent.api.client_v1 import V1WatiClient

    v1 = V1WatiClient(
        base_url=settings.wati_base_url,
        api_token=settings.wati_api_token,
        timeout=HEALTH_CHECK_TIMEOUT,
    )
    try:
        await v1.get_contacts(page_size=1)
        await v1.close()
        real_client = V1WatiClient(
            base_url=settings.wati_base_url,
            api_token=settings.wati_api_token,
        )
        logger.info("wati_api_connected", version="v1")
        return real_client, False, "v1"
    except Exception as e:
        logger.warning("wati_api_health_check_failed", error=str(e))
        await v1.close()

    # Fall back to mock
    from wati_agent.api.mock import MockWatiClient

    return MockWatiClient(), True, "mock"
