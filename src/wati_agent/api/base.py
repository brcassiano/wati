"""Protocol definition for WATI API client."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from wati_agent.api.models import (
    ApiResponse,
    Contact,
    ContactListResponse,
    CustomParam,
    SendTemplateResponse,
    SendTextResponse,
    TemplateListResponse,
)


@runtime_checkable
class WatiClient(Protocol):
    """Interface for WATI API operations (V1 endpoints).

    V1WatiClient and MockWatiClient implement this protocol.
    The architecture supports adding V3 or future versions by
    extending this protocol.
    """

    # --- Contacts ---

    async def get_contacts(
        self, page_size: int = 20, page_number: int = 1
    ) -> ContactListResponse: ...

    async def get_contact(self, target: str) -> Contact: ...

    async def add_contact(
        self,
        whatsapp_number: str,
        name: str,
        custom_params: list[CustomParam] | None = None,
    ) -> Contact: ...

    async def update_contacts(
        self,
        updates: list[dict],
    ) -> ContactListResponse: ...

    # --- Tags ---

    async def add_tag(self, target: str, tag: str) -> ApiResponse: ...

    async def remove_tag(self, target: str, tag: str) -> ApiResponse: ...

    # --- Messages ---

    async def send_text_message(self, target: str, text: str) -> SendTextResponse: ...

    # --- Templates ---

    async def get_templates(
        self, page_size: int = 20, page_number: int = 1
    ) -> TemplateListResponse: ...

    async def send_template_message(
        self,
        template_id: str,
        target: str,
        custom_params: list[CustomParam] | None = None,
    ) -> SendTemplateResponse: ...

    # --- Conversations ---

    async def assign_operator(self, target: str, operator_id: str) -> ApiResponse: ...

    # --- Tickets ---

    async def assign_ticket(self, whatsapp_number: str, team_name: str) -> ApiResponse: ...

    # --- Operators ---

    async def get_operators(self) -> ApiResponse: ...

    # --- Broadcasts ---

    async def send_broadcast_to_segment(
        self, template_name: str, broadcast_name: str, segment_name: str
    ) -> ApiResponse: ...
