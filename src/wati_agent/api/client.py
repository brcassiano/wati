"""Real WATI API client using httpx (V3 endpoints)."""

from __future__ import annotations

from wati_agent.api.http import BaseHttpClient
from wati_agent.api.models import (
    ApiResponse,
    BroadcastDetail,
    BroadcastListResponse,
    ChannelListResponse,
    Contact,
    ContactListResponse,
    ContactUpdateItem,
    CustomParam,
    SendTemplateResponse,
    SendTextResponse,
    TemplateListResponse,
)

V3 = "/api/ext/v3"


class RealWatiClient(BaseHttpClient):
    """HTTP client for WATI API V3 endpoints."""

    def __init__(self, base_url: str, api_token: str, timeout: float = 30.0) -> None:
        super().__init__(base_url, api_token, timeout, log_event="wati_api_call")

    # --- Contacts ---

    async def get_contacts(self, page_size: int = 20, page_number: int = 1) -> ContactListResponse:
        resp = await self._request(
            "GET",
            f"{V3}/contacts",
            params={"page_size": page_size, "page_number": page_number},
        )
        return ContactListResponse.model_validate(resp.json())

    async def get_contact(self, target: str) -> Contact:
        resp = await self._request("GET", f"{V3}/contacts/{target}")
        return Contact.model_validate(resp.json())

    async def add_contact(
        self,
        whatsapp_number: str,
        name: str,
        custom_params: list[CustomParam] | None = None,
    ) -> Contact:
        body: dict = {
            "whatsapp_number": whatsapp_number,
            "name": name,
        }
        if custom_params:
            body["custom_params"] = [p.model_dump() for p in custom_params]
        resp = await self._request("POST", f"{V3}/contacts", json_body=body)
        return Contact.model_validate(resp.json())

    async def update_contacts(self, updates: list[dict]) -> ContactListResponse:
        items = [ContactUpdateItem.model_validate(u) for u in updates]
        body = {"contacts": [i.model_dump(by_alias=True) for i in items]}
        resp = await self._request("PUT", f"{V3}/contacts", json_body=body)
        return ContactListResponse.model_validate(resp.json())

    async def assign_contact_teams(self, target: str, teams: list[str]) -> ApiResponse:
        body = {"target": target, "teams": teams}
        resp = await self._request("PUT", f"{V3}/contacts/teams", json_body=body)
        return ApiResponse.model_validate(resp.json())

    # --- Tags (V3 uses segments, not tags — stub for Protocol compliance) ---

    async def add_tag(self, target: str, tag: str) -> ApiResponse:
        return ApiResponse(
            result=False, message="Tag operations not available in V3 (use segments)"
        )

    async def remove_tag(self, target: str, tag: str) -> ApiResponse:
        return ApiResponse(
            result=False, message="Tag operations not available in V3 (use segments)"
        )

    # --- Messages ---

    async def send_text_message(self, target: str, text: str) -> SendTextResponse:
        body = {"target": target, "text": text}
        resp = await self._request("POST", f"{V3}/conversations/messages/text", json_body=body)
        return SendTextResponse.model_validate(resp.json())

    # --- Templates ---

    async def get_templates(
        self, page_size: int = 20, page_number: int = 1
    ) -> TemplateListResponse:
        resp = await self._request(
            "GET",
            f"{V3}/messageTemplates",
            params={"page_size": page_size, "page_number": page_number},
        )
        return TemplateListResponse.model_validate(resp.json())

    async def send_template_message(
        self,
        template_id: str,
        target: str,
        custom_params: list[CustomParam] | None = None,
    ) -> SendTemplateResponse:
        body: dict = {"template_id": template_id, "target": target}
        if custom_params:
            body["custom_params"] = [p.model_dump() for p in custom_params]
        resp = await self._request("POST", f"{V3}/messageTemplates/send", json_body=body)
        return SendTemplateResponse.model_validate(resp.json())

    # --- Conversations ---

    async def assign_operator(self, target: str, operator_id: str) -> ApiResponse:
        body = {"operator_id": operator_id}
        resp = await self._request("PUT", f"{V3}/conversations/{target}/operator", json_body=body)
        return ApiResponse.model_validate(resp.json())

    async def update_conversation_status(self, target: str, status: str) -> ApiResponse:
        body = {"status": status}
        resp = await self._request("PUT", f"{V3}/conversations/{target}/status", json_body=body)
        return ApiResponse.model_validate(resp.json())

    # --- Tickets (V3 uses operator assignment — stub for Protocol compliance) ---

    async def assign_ticket(self, whatsapp_number: str, team_name: str) -> ApiResponse:
        return ApiResponse(
            result=False, message="Ticket assignment not available in V3 (use assign_operator)"
        )

    # --- Operators ---

    async def get_operators(self) -> ApiResponse:
        return ApiResponse(
            result=False, message="Get operators not available in V3"
        )

    # --- Broadcasts ---

    async def send_broadcast_to_segment(
        self, template_name: str, broadcast_name: str, segment_name: str
    ) -> ApiResponse:
        return ApiResponse(
            result=False, message="Broadcast to segment not available in V3"
        )

    async def get_broadcasts(
        self, page_size: int = 20, page_number: int = 1
    ) -> BroadcastListResponse:
        resp = await self._request(
            "GET",
            f"{V3}/broadcasts",
            params={"page_size": page_size, "page_number": page_number},
        )
        return BroadcastListResponse.model_validate(resp.json())

    async def get_broadcast(self, broadcast_id: str) -> BroadcastDetail:
        resp = await self._request("GET", f"{V3}/broadcasts/{broadcast_id}")
        return BroadcastDetail.model_validate(resp.json())

    # --- Channels ---

    async def get_channels(self) -> ChannelListResponse:
        resp = await self._request("GET", f"{V3}/channels")
        return ChannelListResponse.model_validate(resp.json())
