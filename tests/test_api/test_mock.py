"""Tests for the mock WATI client."""

from __future__ import annotations

import pytest

from wati_agent.api.mock import MockWatiClient
from wati_agent.api.models import CustomParam


@pytest.mark.asyncio
async def test_get_contacts_returns_seeded_data(client: MockWatiClient) -> None:
    result = await client.get_contacts()
    assert len(result.contact_list) == 10
    assert result.page_number == 1


@pytest.mark.asyncio
async def test_get_contacts_pagination(client: MockWatiClient) -> None:
    result = await client.get_contacts(page_size=3, page_number=1)
    assert len(result.contact_list) == 3
    result2 = await client.get_contacts(page_size=3, page_number=2)
    assert len(result2.contact_list) == 3
    # Different contacts
    names1 = {c.name for c in result.contact_list}
    names2 = {c.name for c in result2.contact_list}
    assert names1.isdisjoint(names2)


@pytest.mark.asyncio
async def test_get_contact_by_phone(client: MockWatiClient) -> None:
    contact = await client.get_contact("5511999001122")
    assert contact.name == "Maria Silva"
    assert "VIP" in contact.segments


@pytest.mark.asyncio
async def test_get_contact_not_found(client: MockWatiClient) -> None:
    with pytest.raises(ValueError, match="Contact not found"):
        await client.get_contact("0000000000")


@pytest.mark.asyncio
async def test_add_contact(client: MockWatiClient) -> None:
    contact = await client.add_contact(
        "5511911112222",
        "Novo Contato",
        [CustomParam(name="city", value="Manaus")],
    )
    assert contact.phone == "5511911112222"
    assert contact.name == "Novo Contato"
    # Verify it's persisted
    fetched = await client.get_contact("5511911112222")
    assert fetched.name == "Novo Contato"


@pytest.mark.asyncio
async def test_update_contacts(client: MockWatiClient) -> None:
    result = await client.update_contacts(
        [
            {"target": "5511999001122", "custom_params": [{"name": "city", "value": "Campinas"}]},
        ]
    )
    assert len(result.contact_list) == 1
    updated = result.contact_list[0]
    city = next(p for p in updated.custom_params if p.name == "city")
    assert city.value == "Campinas"


@pytest.mark.asyncio
async def test_get_templates(client: MockWatiClient) -> None:
    result = await client.get_templates()
    assert result.total == 6
    names = {t.name for t in result.template_list}
    assert "renewal_reminder" in names
    assert "flash_sale" in names


@pytest.mark.asyncio
async def test_send_template_message_success(client: MockWatiClient) -> None:
    templates = await client.get_templates()
    tid = templates.template_list[0].id
    result = await client.send_template_message(tid, "5511999001122")
    assert result.result is True
    assert result.status == "sent"


@pytest.mark.asyncio
async def test_send_template_not_found(client: MockWatiClient) -> None:
    result = await client.send_template_message("nonexistent_id", "5511999001122")
    assert result.result is False


@pytest.mark.asyncio
async def test_send_text_message(client: MockWatiClient) -> None:
    result = await client.send_text_message("5511999001122", "Hello!")
    assert result.id is not None
    assert result.event_type == "message"


@pytest.mark.asyncio
async def test_assign_operator(client: MockWatiClient) -> None:
    result = await client.assign_operator("5511999001122", "op123")
    assert result.result is True


@pytest.mark.asyncio
async def test_add_tag(client: MockWatiClient) -> None:
    result = await client.add_tag("5511999001122", "escalated")
    assert result.result is True
    contact = await client.get_contact("5511999001122")
    assert "escalated" in contact.tags


@pytest.mark.asyncio
async def test_add_tag_idempotent(client: MockWatiClient) -> None:
    await client.add_tag("5511999001122", "escalated")
    await client.add_tag("5511999001122", "escalated")
    contact = await client.get_contact("5511999001122")
    assert contact.tags.count("escalated") == 1


@pytest.mark.asyncio
async def test_remove_tag(client: MockWatiClient) -> None:
    await client.add_tag("5511999001122", "temp")
    result = await client.remove_tag("5511999001122", "temp")
    assert result.result is True
    contact = await client.get_contact("5511999001122")
    assert "temp" not in contact.tags


@pytest.mark.asyncio
async def test_remove_tag_not_found(client: MockWatiClient) -> None:
    result = await client.remove_tag("5511999001122", "nonexistent")
    assert result.result is False


@pytest.mark.asyncio
async def test_assign_ticket(client: MockWatiClient) -> None:
    result = await client.assign_ticket("6281234567890", "Support")
    assert result.result is True
    contact = await client.get_contact("6281234567890")
    assert "Support" in contact.teams


@pytest.mark.asyncio
async def test_assign_ticket_contact_not_found(client: MockWatiClient) -> None:
    result = await client.assign_ticket("0000000000", "Support")
    assert result.result is False


@pytest.mark.asyncio
async def test_get_operators(client: MockWatiClient) -> None:
    result = await client.get_operators()
    assert result.result is True
    assert len(result.data["operators"]) == 2


@pytest.mark.asyncio
async def test_send_broadcast_to_segment(client: MockWatiClient) -> None:
    result = await client.send_broadcast_to_segment(
        "flash_sale", "march_sale", "VIP"
    )
    assert result.result is True
    assert "5" in result.message  # 5 VIP contacts


@pytest.mark.asyncio
async def test_send_broadcast_template_not_found(client: MockWatiClient) -> None:
    result = await client.send_broadcast_to_segment(
        "nonexistent", "test", "VIP"
    )
    assert result.result is False


