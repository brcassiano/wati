"""Tests for mock data correctness — segments, contacts, templates."""

from __future__ import annotations

import pytest

from wati_agent.api.mock import MockWatiClient

# --- Contact segments ---


@pytest.mark.asyncio
async def test_mock_has_10_contacts(client: MockWatiClient) -> None:
    result = await client.get_contacts(page_size=100)
    assert len(result.contact_list) == 10


@pytest.mark.asyncio
async def test_vip_contacts_have_vip_segment(client: MockWatiClient) -> None:
    result = await client.get_contacts(page_size=100)
    vip_names = {"Maria Silva", "Joao Santos", "Ana Costa", "Fernanda Lima", "Emily Johnson"}
    for contact in result.contact_list:
        if contact.name in vip_names:
            assert "VIP" in contact.segments, f"{contact.name} should have VIP segment"


@pytest.mark.asyncio
async def test_non_vip_contacts_do_not_have_vip_segment(client: MockWatiClient) -> None:
    result = await client.get_contacts(page_size=100)
    non_vip_names = {"Budi Santoso", "Siti Rahayu", "Carlos Mendes", "James Wilson", "Dewi Lestari"}
    for contact in result.contact_list:
        if contact.name in non_vip_names:
            assert "VIP" not in contact.segments, f"{contact.name} should NOT have VIP segment"


@pytest.mark.asyncio
async def test_exactly_5_non_vip_contacts(client: MockWatiClient) -> None:
    result = await client.get_contacts(page_size=100)
    non_vip = [c for c in result.contact_list if "VIP" not in c.segments]
    assert len(non_vip) == 5


@pytest.mark.asyncio
async def test_exactly_5_vip_contacts(client: MockWatiClient) -> None:
    result = await client.get_contacts(page_size=100)
    vip = [c for c in result.contact_list if "VIP" in c.segments]
    assert len(vip) == 5


@pytest.mark.asyncio
async def test_premium_is_not_vip(client: MockWatiClient) -> None:
    """Premium segment is distinct from VIP."""
    result = await client.get_contacts(page_size=100)
    dewi = next(c for c in result.contact_list if c.name == "Dewi Lestari")
    assert "Premium" in dewi.segments
    assert "VIP" not in dewi.segments


@pytest.mark.asyncio
async def test_all_contacts_have_phone_numbers(client: MockWatiClient) -> None:
    result = await client.get_contacts(page_size=100)
    for contact in result.contact_list:
        assert contact.phone, f"{contact.name} missing phone"
        assert contact.phone.isdigit(), f"{contact.name} phone has non-digits: {contact.phone}"


@pytest.mark.asyncio
async def test_contacts_have_unique_phones(client: MockWatiClient) -> None:
    result = await client.get_contacts(page_size=100)
    phones = [c.phone for c in result.contact_list]
    assert len(phones) == len(set(phones))


# --- Templates ---


@pytest.mark.asyncio
async def test_mock_has_6_templates(client: MockWatiClient) -> None:
    result = await client.get_templates(page_size=100)
    assert len(result.template_list) == 6


@pytest.mark.asyncio
async def test_welcome_template_exists(client: MockWatiClient) -> None:
    result = await client.get_templates(page_size=100)
    names = [t.name for t in result.template_list]
    assert "welcome_message" in names


@pytest.mark.asyncio
async def test_all_templates_approved(client: MockWatiClient) -> None:
    result = await client.get_templates(page_size=100)
    for t in result.template_list:
        assert t.status == "APPROVED", f"Template {t.name} is {t.status}"


# --- Send template with phone number ---


@pytest.mark.asyncio
async def test_send_template_to_phone_number(client: MockWatiClient) -> None:
    """Templates can be sent using phone number as target."""
    templates = await client.get_templates()
    welcome = next(t for t in templates.template_list if t.name == "welcome_message")
    result = await client.send_template_message(welcome.id, "6281234567890")
    assert result.result is True
    assert result.status == "sent"
