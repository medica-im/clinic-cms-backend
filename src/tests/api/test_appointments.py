"""Tests for POST /appointments/ endpoint.

Covers:
- Role-based access: anonymous, staff (non-owner), owner, administrator, superuser
- Input variants: url-based, phone-based, Office, HouseCall, no location
- Validation: both url+phone, neither url nor phone
"""

import pytest
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch
from tests.conftest import FakeNode, FakeRelationship


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------

URL_OFFICE_PAYLOAD = {
    "entry": "entry-uid-001",
    "url": "https://rdv.example.com",
    "phone": None,
    "location": "office",
}

PHONE_OFFICE_PAYLOAD = {
    "entry": "entry-uid-001",
    "url": None,
    "phone": "+33412345678",
    "location": "office",
}

URL_HOUSE_CALL_PAYLOAD = {
    "entry": "entry-uid-001",
    "url": "https://rdv.example.com/domicile",
    "phone": None,
    "location": "house_call",
}

PHONE_HOUSE_CALL_PAYLOAD = {
    "entry": "entry-uid-001",
    "url": None,
    "phone": "+33412345678",
    "location": "house_call",
}

URL_NO_LOCATION_PAYLOAD = {
    "entry": "entry-uid-001",
    "url": "https://rdv.example.com",
    "phone": None,
    "location": None,
}

PHONE_NO_LOCATION_PAYLOAD = {
    "entry": "entry-uid-001",
    "url": None,
    "phone": "+33412345678",
    "location": None,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _neo4j_create_mocks(fake_entry, appt_class_name, expected_location, url=None, phone=None):
    """Build the context managers needed to mock Neo4j for appointment creation."""
    appt_node = FakeNode(
        uid="new-appt-uid",
        url=url,
        phone=phone,
        _labels=_labels_for_location(expected_location),
    )
    appt_node.entry = FakeRelationship([fake_entry])

    return [
        patch("api.routers.appointment.get_entry", new_callable=AsyncMock, return_value=fake_entry),
        patch("api.routers.appointment.get_entry_users", new_callable=AsyncMock, return_value=fake_entry.owner._nodes),
        patch("api.auth.is_user_in_authorized_list", new_callable=AsyncMock, return_value=False),
        patch("api.asyncserializers.appointment.same_nodes", new_callable=AsyncMock, return_value=[]),
        patch("api.asyncserializers.appointment.adb.cypher_query", new_callable=AsyncMock, return_value=([], [])),
        patch("directory.models.agraph.Appointment.save", new_callable=AsyncMock, return_value=None),
        patch("directory.models.agraph.Office.save", new_callable=AsyncMock, return_value=None),
        patch("directory.models.agraph.HouseCall.save", new_callable=AsyncMock, return_value=None),
        patch(f"api.asyncserializers.appointment.{appt_class_name}", return_value=appt_node),
        patch("api.asyncserializers.appointment.get_location", new_callable=AsyncMock, return_value=expected_location),
    ]


def _labels_for_location(location):
    if location == "office":
        return ["Appointment", "Office"]
    elif location == "house_call":
        return ["Appointment", "HouseCall"]
    return ["Appointment"]


def _enter_all(stack, patch_jwt_fn, jwt, mock_neo4j_role_fn, role, mock_get_site_cm, mocks):
    """Enter all context managers via an ExitStack."""
    stack.enter_context(patch_jwt_fn(jwt))
    stack.enter_context(mock_neo4j_role_fn(role))
    stack.enter_context(mock_get_site_cm)
    for m in mocks:
        stack.enter_context(m)


# ===================================================================
# ACCESS CONTROL TESTS
# ===================================================================

@pytest.mark.asyncio
async def test_create_appointment_anonymous_returns_401(client):
    """No JWT cookie → 401."""
    response = await client.post("/appointments/", json=URL_OFFICE_PAYLOAD)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_appointment_as_owner_returns_200(
    client, patch_jwt, jwt_owner, mock_neo4j_role, mock_get_site, site, appointments_acl,
    fake_entry,
):
    """Entry owner can create an appointment (object-level permission bypass)."""
    mocks = _neo4j_create_mocks(fake_entry, "Office", "office", url="https://rdv.example.com")
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_owner, mock_neo4j_role, None, mock_get_site, mocks)
        stack.enter_context(patch("api.auth.is_user_in_authorized_list", new_callable=AsyncMock, return_value=True))
        response = await client.post("/appointments/", json=URL_OFFICE_PAYLOAD)
    assert response.status_code == 200
    data = response.json()
    assert data["entry"] == "entry-uid-001"
    assert data["url"] == "https://rdv.example.com"
    assert data["location"] == "office"


@pytest.mark.asyncio
async def test_create_appointment_as_staff_non_owner_returns_403(
    client, patch_jwt, jwt_staff, mock_neo4j_role, mock_get_site, site, appointments_acl,
    fake_entry,
):
    """Staff user who is NOT the owner → 403 (staff has read-only permission for appointments)."""
    with ExitStack() as stack:
        stack.enter_context(patch_jwt(jwt_staff))
        stack.enter_context(mock_neo4j_role("staff"))
        stack.enter_context(mock_get_site)
        stack.enter_context(patch("api.routers.appointment.get_entry", new_callable=AsyncMock, return_value=fake_entry))
        stack.enter_context(patch("api.routers.appointment.get_entry_users", new_callable=AsyncMock, return_value=fake_entry.owner._nodes))
        stack.enter_context(patch("api.auth.is_user_in_authorized_list", new_callable=AsyncMock, return_value=False))
        response = await client.post("/appointments/", json=URL_OFFICE_PAYLOAD)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_appointment_as_administrator_returns_200(
    client, patch_jwt, jwt_administrator, mock_neo4j_role, mock_get_site, site, appointments_acl,
    fake_entry,
):
    """Administrator can create appointments on any entry."""
    mocks = _neo4j_create_mocks(fake_entry, "Office", "office", url="https://rdv.example.com")
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_administrator, mock_neo4j_role, "administrator", mock_get_site, mocks)
        response = await client.post("/appointments/", json=URL_OFFICE_PAYLOAD)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_create_appointment_as_superuser_returns_200(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, site, appointments_acl,
    fake_entry,
):
    """Superuser can create appointments on any entry."""
    mocks = _neo4j_create_mocks(fake_entry, "Office", "office", url="https://rdv.example.com")
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, mock_neo4j_role, "superuser", mock_get_site, mocks)
        response = await client.post("/appointments/", json=URL_OFFICE_PAYLOAD)
    assert response.status_code == 200


# ===================================================================
# INPUT VARIANT TESTS (all as superuser to isolate input logic)
# ===================================================================

@pytest.mark.asyncio
async def test_create_appointment_url_office(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, site, appointments_acl,
    fake_entry,
):
    """URL-based Office appointment."""
    mocks = _neo4j_create_mocks(fake_entry, "Office", "office", url="https://rdv.example.com")
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, mock_neo4j_role, "superuser", mock_get_site, mocks)
        response = await client.post("/appointments/", json=URL_OFFICE_PAYLOAD)
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://rdv.example.com"
    assert data["phone"] is None
    assert data["location"] == "office"


@pytest.mark.asyncio
async def test_create_appointment_phone_office(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, site, appointments_acl,
    fake_entry,
):
    """Phone-based Office appointment."""
    mocks = _neo4j_create_mocks(fake_entry, "Office", "office", phone="+33412345678")
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, mock_neo4j_role, "superuser", mock_get_site, mocks)
        response = await client.post("/appointments/", json=PHONE_OFFICE_PAYLOAD)
    assert response.status_code == 200
    data = response.json()
    assert data["phone"] == "+33412345678"
    assert data["url"] is None
    assert data["location"] == "office"


@pytest.mark.asyncio
async def test_create_appointment_url_house_call(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, site, appointments_acl,
    fake_entry,
):
    """URL-based HouseCall appointment."""
    mocks = _neo4j_create_mocks(fake_entry, "HouseCall", "house_call", url="https://rdv.example.com/domicile")
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, mock_neo4j_role, "superuser", mock_get_site, mocks)
        response = await client.post("/appointments/", json=URL_HOUSE_CALL_PAYLOAD)
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://rdv.example.com/domicile"
    assert data["location"] == "house_call"


@pytest.mark.asyncio
async def test_create_appointment_phone_house_call(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, site, appointments_acl,
    fake_entry,
):
    """Phone-based HouseCall appointment."""
    mocks = _neo4j_create_mocks(fake_entry, "HouseCall", "house_call", phone="+33412345678")
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, mock_neo4j_role, "superuser", mock_get_site, mocks)
        response = await client.post("/appointments/", json=PHONE_HOUSE_CALL_PAYLOAD)
    assert response.status_code == 200
    data = response.json()
    assert data["phone"] == "+33412345678"
    assert data["location"] == "house_call"


@pytest.mark.asyncio
async def test_create_appointment_url_no_location(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, site, appointments_acl,
    fake_entry,
):
    """URL-based appointment with no location (plain Appointment, not Office/HouseCall)."""
    mocks = _neo4j_create_mocks(fake_entry, "Appointment", None, url="https://rdv.example.com")
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, mock_neo4j_role, "superuser", mock_get_site, mocks)
        response = await client.post("/appointments/", json=URL_NO_LOCATION_PAYLOAD)
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://rdv.example.com"
    assert data["location"] is None


@pytest.mark.asyncio
async def test_create_appointment_phone_no_location(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, site, appointments_acl,
    fake_entry,
):
    """Phone-based appointment with no location."""
    mocks = _neo4j_create_mocks(fake_entry, "Appointment", None, phone="+33412345678")
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, mock_neo4j_role, "superuser", mock_get_site, mocks)
        response = await client.post("/appointments/", json=PHONE_NO_LOCATION_PAYLOAD)
    assert response.status_code == 200
    data = response.json()
    assert data["phone"] == "+33412345678"
    assert data["location"] is None


# ===================================================================
# VALIDATION TESTS
# ===================================================================

@pytest.mark.asyncio
async def test_create_appointment_both_url_and_phone_returns_422(
    client, patch_jwt, jwt_superuser,
):
    """Both url and phone set → 422 validation error."""
    payload = {
        "entry": "entry-uid-001",
        "url": "https://rdv.example.com",
        "phone": "+33412345678",
        "location": "office",
    }
    with patch_jwt(jwt_superuser):
        response = await client.post("/appointments/", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_appointment_neither_url_nor_phone_returns_422(
    client, patch_jwt, jwt_superuser,
):
    """Both url and phone are None → 422 validation error."""
    payload = {
        "entry": "entry-uid-001",
        "url": None,
        "phone": None,
        "location": "office",
    }
    with patch_jwt(jwt_superuser):
        response = await client.post("/appointments/", json=payload)
    assert response.status_code == 422
