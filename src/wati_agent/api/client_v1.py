"""WATI API V1 client — for trial/legacy accounts that don't support V3."""

from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone

from wati_agent.api.http import BaseHttpClient
from wati_agent.api.models import (
    ApiResponse,
    BroadcastDetail,
    BroadcastListResponse,
    BroadcastStatistics,
    ChannelListResponse,
    Contact,
    ContactListResponse,
    CustomParam,
    MessageTemplate,
    SendTemplateResponse,
    SendTextResponse,
    TemplateListResponse,
)

V1 = "/api/v1"


class V1WatiClient(BaseHttpClient):
    """HTTP client for WATI API V1 endpoints.

    Adapts V1 responses to the same models used by the V3 client,
    so the agent layer doesn't need to know which version is active.
    """

    def __init__(self, base_url: str, api_token: str, timeout: float = 30.0) -> None:
        super().__init__(base_url, api_token, timeout, log_event="wati_v1_api_call")

    # --- Contacts ---

    async def get_contacts(self, page_size: int = 20, page_number: int = 1) -> ContactListResponse:
        resp = await self._request(
            "GET",
            f"{V1}/contacts",
            params={"pageSize": page_size, "pageNumber": page_number},
        )
        data = resp.json()
        # V1 returns {"ok": true, "result": [...]}
        raw_contacts = data.get("result", [])
        if not isinstance(raw_contacts, list):
            raw_contacts = []
        contacts = []
        for c in raw_contacts:
            # V1 dates can be "Mar-26-2026" or ISO format — skip if unparseable
            created = None
            last_updated = None
            try:
                if c.get("lastUpdated"):
                    last_updated = c["lastUpdated"]
            except (ValueError, TypeError):
                pass

            # Parse customParams defensively — V1 format can vary
            raw_params = c.get("customParams") or []
            parsed_params: list[CustomParam] = []
            if isinstance(raw_params, list):
                for p in raw_params:
                    if not isinstance(p, dict):
                        continue
                    pname = p.get("name") or p.get("paramName") or ""
                    pvalue = p.get("value") if p.get("value") is not None else p.get("paramValue")
                    if pname and pvalue is not None:
                        parsed_params.append(CustomParam(name=pname, value=str(pvalue)))

            contacts.append(
                Contact(
                    id=c.get("id", ""),
                    wa_id=c.get("wAid", c.get("whatsappNumber", "")),
                    name=c.get("fullName", c.get("firstName", "")),
                    phone=c.get("phone", c.get("wAid", "")),
                    created=created,
                    last_updated=last_updated,
                    contact_status=c.get("contactStatus"),
                    opted_in=c.get("optedIn", False),
                    allow_broadcast=c.get("allowBroadcast", False),
                    custom_params=parsed_params,
                )
            )
        return ContactListResponse(
            contact_list=contacts,
            page_number=page_number,
            page_size=page_size,
        )

    async def get_contact(self, target: str) -> Contact:
        # V1 has no reliable single-contact endpoint — fall back to list + filter
        try:
            resp = await self._request("GET", f"{V1}/getContacts/{target}")
            data = resp.json()
            c = data if isinstance(data, dict) else {}
            return Contact(
                id=c.get("id", ""),
                wa_id=target,
                name=c.get("fullName", c.get("name", "")),
                phone=target,
            )
        except Exception:
            # Fallback: fetch all contacts and find by phone
            result = await self.get_contacts(page_size=100)
            for c in result.contact_list:
                if c.phone == target or c.wa_id == target:
                    return c
            raise ValueError(f"Contact not found: {target}")

    async def add_contact(
        self,
        whatsapp_number: str,
        name: str,
        custom_params: list[CustomParam] | None = None,
    ) -> Contact:
        body: dict = {"name": name}
        if custom_params:
            body["customParams"] = [{"name": p.name, "value": p.value} for p in custom_params]
        resp = await self._request("POST", f"{V1}/addContact/{whatsapp_number}", json_body=body)
        data = resp.json()
        if not data.get("result", True):
            raise ValueError(data.get("info", "Failed to add contact"))
        return Contact(
            id=str(uuid.uuid4()),
            wa_id=whatsapp_number,
            name=name,
            phone=whatsapp_number,
            created=datetime.now(timezone.utc),
        )

    async def update_contacts(self, updates: list[dict]) -> ContactListResponse:
        # V1 doesn't have a batch update — do it one by one
        updated = []
        for item in updates:
            target = item.get("target", "")
            params = item.get("custom_params", item.get("customParams", []))
            body = {"customParams": params}
            try:
                await self._request(
                    "POST",
                    f"{V1}/updateContactAttributes/{target}",
                    json_body=body,
                )
                updated.append(Contact(phone=target, wa_id=target))
            except Exception:
                pass
        return ContactListResponse(
            contact_list=updated,
            page_number=1,
            page_size=len(updated),
        )

    async def assign_contact_teams(self, target: str, teams: list[str]) -> ApiResponse:
        # V1 doesn't have team assignment
        return ApiResponse(result=False, message="Team assignment not available in V1 API")

    # --- Tags ---

    async def add_tag(self, target: str, tag: str) -> ApiResponse:
        resp = await self._request(
            "POST",
            f"{V1}/addTag/{target}",
            json_body={"tag": tag},
        )
        data = resp.json()
        if not data.get("result", True):
            return ApiResponse(result=False, message=data.get("info", "Failed to add tag"))
        return ApiResponse(result=True, message=f"Tag '{tag}' added")

    async def remove_tag(self, target: str, tag: str) -> ApiResponse:
        resp = await self._request("DELETE", f"{V1}/removeTag/{target}/{tag}")
        data = resp.json()
        if not data.get("result", True):
            return ApiResponse(result=False, message=data.get("info", "Failed to remove tag"))
        return ApiResponse(result=True, message=f"Tag '{tag}' removed")

    # --- Messages ---

    async def send_text_message(self, target: str, text: str) -> SendTextResponse:
        resp = await self._request(
            "POST",
            f"{V1}/sendSessionMessage/{target}",
            params={"messageText": text},
        )
        data = resp.json()
        if not data.get("result", True):
            raise ValueError(data.get("info", "Failed to send message"))
        return SendTextResponse(
            id=str(uuid.uuid4()),
            created=datetime.now(timezone.utc),
            event_type="message",
        )

    # --- Templates ---

    async def get_templates(
        self, page_size: int = 20, page_number: int = 1
    ) -> TemplateListResponse:
        resp = await self._request("GET", f"{V1}/getMessageTemplates")
        data = resp.json()
        raw = data.get("messageTemplates", [])
        templates = []
        for t in raw:
            lang = t.get("language", {})
            lang_str = lang.get("value", "") if isinstance(lang, dict) else str(lang)
            # Extract body and required custom params
            body = t.get("body") or t.get("hsm") or ""
            raw_params = t.get("customParams") or []
            tpl_params = [
                CustomParam(name=p["paramName"], value=p.get("paramValue", ""))
                for p in raw_params
                if p.get("paramName")
            ]
            # V1 often returns empty customParams even when body has {{1}}, {{2}}.
            # Auto-extract param placeholders from body so the LLM knows what to fill.
            if not tpl_params and body:
                placeholders = sorted(set(re.findall(r"\{\{(\d+)\}\}", body)))
                tpl_params = [CustomParam(name=p, value="") for p in placeholders]
            templates.append(
                MessageTemplate(
                    id=t.get("id", ""),
                    name=t.get("elementName", ""),
                    status=t.get("status", ""),
                    category=t.get("category"),
                    language=lang_str,
                    body=body,
                    custom_params=tpl_params,
                    last_updated=t.get("lastModified"),
                )
            )
        # Manual pagination
        start = (page_number - 1) * page_size
        page = templates[start : start + page_size]
        return TemplateListResponse(
            template_list=page,
            page_number=page_number,
            page_size=page_size,
            total=len(templates),
        )

    async def send_template_message(
        self,
        template_id: str,
        target: str,
        custom_params: list[CustomParam] | None = None,
    ) -> SendTemplateResponse:
        # V1 uses template name (elementName), not ID.
        # The agent may pass either — we use it as template_name.
        body = {
            "template_name": template_id,
            "broadcast_name": f"agent_{int(time.time())}",
            "receivers": [
                {
                    "whatsappNumber": target,
                    "customParams": [
                        {"name": p.name, "value": p.value} for p in (custom_params or [])
                    ],
                }
            ],
        }
        resp = await self._request("POST", f"{V1}/sendTemplateMessages", json_body=body)
        data = resp.json()

        # Check for errors — V1 can return result:true but with errors
        errors = data.get("errors", {})
        error_msg = errors.get("error", "")
        invalid_params = errors.get("invalidCustomParameters", [])
        invalid_numbers = errors.get("invalidWhatsappNumbers", [])

        if invalid_params or invalid_numbers or error_msg:
            parts = []
            if error_msg:
                parts.append(error_msg)
            parts.extend(invalid_params)
            parts.extend(invalid_numbers)
            return SendTemplateResponse(result=False, status=". ".join(parts))

        if not data.get("result", False):
            info = data.get("info", "Failed to send template")
            return SendTemplateResponse(result=False, status=info)

        return SendTemplateResponse(
            result=True,
            message_id=str(uuid.uuid4()),
            status="sent",
        )

    # --- Conversations ---

    async def assign_operator(self, target: str, operator_id: str) -> ApiResponse:
        resp = await self._request(
            "POST",
            f"{V1}/assignOperator/{target}",
            json_body={"email": operator_id},
        )
        data = resp.json()
        if not data.get("result", True):
            return ApiResponse(
                result=False, message=data.get("info", "Failed to assign operator")
            )
        return ApiResponse(result=True, message=f"Operator {operator_id} assigned")

    async def update_conversation_status(self, target: str, status: str) -> ApiResponse:
        # V1 doesn't have conversation status update
        return ApiResponse(
            result=False,
            message="Conversation status update not available in V1 API",
        )

    # --- Tickets ---

    async def assign_ticket(self, whatsapp_number: str, team_name: str) -> ApiResponse:
        resp = await self._request(
            "POST",
            f"{V1}/tickets/assign",
            json_body={"whatsappNumber": whatsapp_number, "teamName": team_name},
        )
        data = resp.json()
        if not data.get("result", True):
            return ApiResponse(result=False, message=data.get("info", "Failed to assign ticket"))
        return ApiResponse(result=True, message=f"Ticket assigned to {team_name}")

    # --- Operators ---

    async def get_operators(self) -> ApiResponse:
        resp = await self._request("GET", f"{V1}/getOperators")
        data = resp.json()
        return ApiResponse(
            result=True, data={"operators": data.get("result", [])}
        )

    # --- Broadcasts ---

    async def send_broadcast_to_segment(
        self, template_name: str, broadcast_name: str, segment_name: str
    ) -> ApiResponse:
        body = {
            "template_name": template_name,
            "broadcast_name": broadcast_name,
            "segmentName": segment_name,
        }
        resp = await self._request(
            "POST", f"{V1}/sendBroadcastToSegment", json_body=body
        )
        data = resp.json()
        if not data.get("result", True):
            return ApiResponse(
                result=False,
                message=data.get("info", "Failed to send broadcast"),
            )
        return ApiResponse(result=True, message="Broadcast sent")

    async def get_broadcasts(
        self, page_size: int = 20, page_number: int = 1
    ) -> BroadcastListResponse:
        return BroadcastListResponse(broadcasts=[], total=0)

    async def get_broadcast(self, broadcast_id: str) -> BroadcastDetail:
        return BroadcastDetail(
            id=broadcast_id,
            statistics=BroadcastStatistics(),
        )

    # --- Channels ---

    async def get_channels(self) -> ChannelListResponse:
        return ChannelListResponse(channels=[])
