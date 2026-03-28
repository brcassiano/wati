"""Mock WATI API client with in-memory state for testing and fallback."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from wati_agent.api.models import (
    ApiResponse,
    Contact,
    ContactListResponse,
    CustomParam,
    MessageTemplate,
    SendTemplateResponse,
    SendTextResponse,
    TemplateListResponse,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MockWatiClient:
    """In-memory mock with realistic seed data. Stateful per instance."""

    def __init__(self) -> None:
        self._contacts: dict[str, Contact] = {}
        self._templates: dict[str, MessageTemplate] = {}
        self._seed_data()

    def _seed_data(self) -> None:
        """Populate with realistic sample data."""
        contacts = [
            ("5511999001122", "Maria Silva", ["VIP"], [("city", "Sao Paulo")]),
            ("5511988003344", "Joao Santos", ["VIP"], [("city", "Rio de Janeiro")]),
            ("5511977005566", "Ana Costa", ["VIP", "Premium"], [("city", "Jakarta")]),
            ("6281234567890", "Budi Santoso", ["Standard"], [("city", "Jakarta")]),
            ("6289876543210", "Siti Rahayu", ["Standard"], [("city", "Bandung")]),
            ("5511966007788", "Carlos Mendes", ["Lead"], [("city", "Belo Horizonte")]),
            ("5511955009900", "Fernanda Lima", ["Lead", "VIP"], [("city", "Curitiba")]),
            ("447911123456", "James Wilson", ["International"], [("city", "London")]),
            ("14155552671", "Emily Johnson", ["International", "VIP"], [("city", "San Francisco")]),
            ("6282345678901", "Dewi Lestari", ["Premium"], [("city", "Surabaya")]),
        ]
        for phone, name, segments, params in contacts:
            self._contacts[phone] = Contact(
                id=str(uuid.uuid4()),
                wa_id=phone,
                name=name,
                phone=phone,
                created=_now(),
                last_updated=_now(),
                contact_status="valid",
                opted_in=True,
                allow_broadcast=True,
                segments=segments,
                custom_params=[CustomParam(name=k, value=v) for k, v in params],
            )

        templates: list[tuple[str, str, str, str, str, list[CustomParam]]] = [
            (
                "renewal_reminder",
                "APPROVED",
                "MARKETING",
                "en",
                "Hi {{1}}, your subscription expires on {{2}}. Renew now to keep your benefits!",
                [CustomParam(name="1", value="name"), CustomParam(name="2", value="date")],
            ),
            (
                "flash_sale",
                "APPROVED",
                "MARKETING",
                "en",
                "Hey {{1}}! Flash sale: {{2}}% off everything until {{3}}. Shop now!",
                [
                    CustomParam(name="1", value="name"),
                    CustomParam(name="2", value="discount"),
                    CustomParam(name="3", value="end_date"),
                ],
            ),
            (
                "welcome_message",
                "APPROVED",
                "UTILITY",
                "en",
                "Welcome {{1}}! We're glad to have you. Reply HELP anytime for assistance.",
                [CustomParam(name="1", value="name")],
            ),
            (
                "order_confirmation",
                "APPROVED",
                "UTILITY",
                "en",
                "Hi {{1}}, your order #{{2}} has been confirmed. Estimated delivery: {{3}}.",
                [
                    CustomParam(name="1", value="name"),
                    CustomParam(name="2", value="order_id"),
                    CustomParam(name="3", value="delivery_date"),
                ],
            ),
            (
                "appointment_reminder",
                "APPROVED",
                "UTILITY",
                "en",
                "Reminder: {{1}}, your appointment is on {{2}} at {{3}}. Reply YES to confirm.",
                [
                    CustomParam(name="1", value="name"),
                    CustomParam(name="2", value="date"),
                    CustomParam(name="3", value="time"),
                ],
            ),
            (
                "feedback_request",
                "APPROVED",
                "MARKETING",
                "en",
                "Hi {{1}}, how was your experience? Rate us 1-5 by replying to this message.",
                [CustomParam(name="1", value="name")],
            ),
        ]
        for name, status, category, lang, body, params in templates:
            tid = str(uuid.uuid4())
            self._templates[tid] = MessageTemplate(
                id=tid,
                name=name,
                status=status,
                category=category,
                language=lang,
                body=body,
                custom_params=params,
                created=_now(),
                last_updated=_now(),
            )

    # --- Contacts ---

    async def get_contacts(self, page_size: int = 20, page_number: int = 1) -> ContactListResponse:
        all_contacts = list(self._contacts.values())
        start = (page_number - 1) * page_size
        page = all_contacts[start : start + page_size]
        return ContactListResponse(contact_list=page, page_number=page_number, page_size=page_size)

    async def get_contact(self, target: str) -> Contact:
        # Search by phone or id
        if target in self._contacts:
            return self._contacts[target]
        for c in self._contacts.values():
            if c.id == target:
                return c
        raise ValueError(f"Contact not found: {target}")

    async def add_contact(
        self,
        whatsapp_number: str,
        name: str,
        custom_params: list[CustomParam] | None = None,
    ) -> Contact:
        contact = Contact(
            id=str(uuid.uuid4()),
            wa_id=whatsapp_number,
            name=name,
            phone=whatsapp_number,
            created=_now(),
            last_updated=_now(),
            contact_status="valid",
            opted_in=True,
            custom_params=custom_params or [],
        )
        self._contacts[whatsapp_number] = contact
        return contact

    async def update_contacts(self, updates: list[dict]) -> ContactListResponse:
        updated = []
        for item in updates:
            target = item["target"]
            contact = self._contacts.get(target)
            if not contact:
                continue
            params = item.get("custom_params", item.get("customParams", []))
            for p in params:
                cp = CustomParam(name=p["name"], value=p["value"])
                existing = [i for i, x in enumerate(contact.custom_params) if x.name == cp.name]
                if existing:
                    contact.custom_params[existing[0]] = cp
                else:
                    contact.custom_params.append(cp)
            contact.last_updated = _now()
            updated.append(contact)
        return ContactListResponse(contact_list=updated, page_number=1, page_size=len(updated))

    # --- Tags ---

    async def add_tag(self, target: str, tag: str) -> ApiResponse:
        contact = self._contacts.get(target)
        if not contact:
            return ApiResponse(result=False, message=f"Contact not found: {target}")
        if tag not in contact.tags:
            contact.tags.append(tag)
        return ApiResponse(result=True, message=f"Tag '{tag}' added to {target}")

    async def remove_tag(self, target: str, tag: str) -> ApiResponse:
        contact = self._contacts.get(target)
        if not contact:
            return ApiResponse(result=False, message=f"Contact not found: {target}")
        if tag in contact.tags:
            contact.tags.remove(tag)
            return ApiResponse(result=True, message=f"Tag '{tag}' removed from {target}")
        return ApiResponse(result=False, message=f"Tag '{tag}' not found on {target}")

    # --- Messages ---

    async def send_text_message(self, target: str, text: str) -> SendTextResponse:
        return SendTextResponse(
            id=str(uuid.uuid4()),
            created=_now(),
            conversation_id=str(uuid.uuid4()),
            event_type="message",
        )

    # --- Templates ---

    async def get_templates(
        self, page_size: int = 20, page_number: int = 1
    ) -> TemplateListResponse:
        all_templates = list(self._templates.values())
        start = (page_number - 1) * page_size
        page = all_templates[start : start + page_size]
        return TemplateListResponse(
            template_list=page,
            page_number=page_number,
            page_size=page_size,
            total=len(all_templates),
        )

    async def send_template_message(
        self,
        template_id: str,
        target: str,
        custom_params: list[CustomParam] | None = None,
    ) -> SendTemplateResponse:
        template = self._templates.get(template_id)
        if not template:
            for t in self._templates.values():
                if t.name == template_id:
                    template = t
                    break
        if not template:
            return SendTemplateResponse(result=False, status="template_not_found")
        return SendTemplateResponse(
            result=True,
            message_id=str(uuid.uuid4()),
            status="sent",
        )

    # --- Conversations ---

    async def assign_operator(self, target: str, operator_id: str) -> ApiResponse:
        return ApiResponse(result=True, message=f"Operator {operator_id} assigned to {target}")

    # --- Tickets ---

    async def assign_ticket(self, whatsapp_number: str, team_name: str) -> ApiResponse:
        contact = self._contacts.get(whatsapp_number)
        if not contact:
            return ApiResponse(result=False, message=f"Contact not found: {whatsapp_number}")
        if team_name not in contact.teams:
            contact.teams.append(team_name)
        return ApiResponse(
            result=True, message=f"Ticket assigned to {team_name} for {whatsapp_number}"
        )

    # --- Operators ---

    async def get_operators(self) -> ApiResponse:
        operators = [
            {"id": "op_001", "email": "agent@company.com", "name": "Agent Smith"},
            {"id": "op_002", "email": "support@company.com", "name": "Support Lead"},
        ]
        return ApiResponse(result=True, data={"operators": operators})

    # --- Broadcasts ---

    async def send_broadcast_to_segment(
        self, template_name: str, broadcast_name: str, segment_name: str
    ) -> ApiResponse:
        found = any(t.name == template_name for t in self._templates.values())
        if not found:
            return ApiResponse(
                result=False, message=f"Template '{template_name}' not found"
            )
        matches = [
            c for c in self._contacts.values() if segment_name in c.segments
        ]
        return ApiResponse(
            result=True,
            message=f"Broadcast '{broadcast_name}' sent to {len(matches)} contacts",
        )
