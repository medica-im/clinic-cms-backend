"""Tests for POST /users/export/listmonk and POST /invitees/export/listmonk.

Covers:
- Role-based access: anonymous, staff, administrator, superuser
- Organization lookup failures (missing org, missing neomodel_uid)
- CSV content: header, attributes JSON, skip rows with no email
- Deduplication: only one row per email address (invitees export)
"""

import csv
import io
import pytest
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch


ORG_NAME = "Test Org"
ORG_FORMATTED_NAME = "Cabinet Test"
ENTRY_UID = "entry-uid-001"


class FakeOrganization:
    def __init__(self, neomodel_uid=ENTRY_UID, name=ORG_NAME, formatted_name=ORG_FORMATTED_NAME):
        self.neomodel_uid = _FakeHexUid(neomodel_uid) if neomodel_uid else None
        self.name = name
        self.formatted_name = formatted_name


class _FakeHexUid:
    def __init__(self, value):
        self.hex = value


def _org_mocks(org, cypher_results):
    return [
        patch("api.routers.listmonk_export.Organization.objects.aget", new_callable=AsyncMock, return_value=org),
        patch("api.routers.listmonk_export.adb.cypher_query", new_callable=AsyncMock, return_value=(cypher_results, [])),
    ]


def _enter_all(stack, patch_jwt_fn, jwt, role, site, mocks=()):
    stack.enter_context(patch_jwt_fn(jwt))
    stack.enter_context(patch("api.routers.listmonk_export.get_neo4j_role", new_callable=AsyncMock, return_value=role))
    stack.enter_context(patch("api.routers.listmonk_export.get_site_from_request", new_callable=AsyncMock, return_value=site))
    for m in mocks:
        stack.enter_context(m)


def _read_csv(content: bytes):
    return list(csv.reader(io.StringIO(content.decode("utf-8"))))


# ===================================================================
# ACCESS CONTROL — /users/export/listmonk
# ===================================================================

@pytest.mark.asyncio
async def test_export_users_anonymous_returns_401(client):
    response = await client.post("/users/export/listmonk", json={"user_uids": ["u1"]})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_export_users_as_staff_returns_403(
    client, patch_jwt, jwt_staff, site,
):
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_staff, "staff", site)
        response = await client.post("/users/export/listmonk", json={"user_uids": ["u1"]})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_export_users_as_administrator_returns_403(
    client, patch_jwt, jwt_administrator, site,
):
    """Only superuser role is authorized — administrator is not enough."""
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_administrator, "administrator", site)
        response = await client.post("/users/export/listmonk", json={"user_uids": ["u1"]})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_export_users_as_superuser_returns_200(
    client, patch_jwt, jwt_superuser, site,
):
    org = FakeOrganization()
    results = [["u1", "user1@example.com", "User One"]]
    mocks = _org_mocks(org, results)
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, "superuser", site, mocks)
        response = await client.post("/users/export/listmonk", json={"user_uids": ["u1"]})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = _read_csv(response.content)
    assert rows[0] == ["email", "name", "attributes"]
    assert rows[1][0] == "user1@example.com"
    assert rows[1][1] == "User One"


@pytest.mark.asyncio
async def test_export_users_org_not_found_returns_404(
    client, patch_jwt, jwt_superuser, site,
):
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, "superuser", site)
        stack.enter_context(patch(
            "api.routers.listmonk_export.Organization.objects.aget",
            new_callable=AsyncMock,
            side_effect=__import__("facility.models", fromlist=["Organization"]).Organization.DoesNotExist,
        ))
        response = await client.post("/users/export/listmonk", json={"user_uids": ["u1"]})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_export_users_org_without_neomodel_uid_returns_404(
    client, patch_jwt, jwt_superuser, site,
):
    org = FakeOrganization(neomodel_uid=None)
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, "superuser", site, [
            patch("api.routers.listmonk_export.Organization.objects.aget", new_callable=AsyncMock, return_value=org),
        ])
        response = await client.post("/users/export/listmonk", json={"user_uids": ["u1"]})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_export_users_skips_rows_without_email(
    client, patch_jwt, jwt_superuser, site,
):
    org = FakeOrganization()
    results = [
        ["u1", "user1@example.com", "User One"],
        ["u2", None, "No Email User"],
    ]
    mocks = _org_mocks(org, results)
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, "superuser", site, mocks)
        response = await client.post("/users/export/listmonk", json={"user_uids": ["u1", "u2"]})
    assert response.status_code == 200
    rows = _read_csv(response.content)
    assert len(rows) == 2  # header + 1 data row
    assert rows[1][0] == "user1@example.com"


@pytest.mark.asyncio
async def test_export_users_attributes_json_structure(
    client, patch_jwt, jwt_superuser, site,
):
    import json as jsonlib
    org = FakeOrganization()
    results = [["u1", "user1@example.com", "User One"]]
    mocks = _org_mocks(org, results)
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, "superuser", site, mocks)
        response = await client.post("/users/export/listmonk", json={"user_uids": ["u1"]})
    rows = _read_csv(response.content)
    attributes = jsonlib.loads(rows[1][2])
    assert attributes["pluriproweb"]["user"]["uid"] == "u1"
    assert attributes["pluriproweb"]["user"]["name"] == "User One"
    assert attributes["pluriproweb"]["organization"]["name"] == ORG_NAME
    assert attributes["pluriproweb"]["organization"]["neomodel_uid"] == ENTRY_UID
    assert attributes["pluriproweb"]["organization"]["formatted_name"] == ORG_FORMATTED_NAME


# ===================================================================
# ACCESS CONTROL — /invitees/export/listmonk
# ===================================================================

@pytest.mark.asyncio
async def test_export_invitees_anonymous_returns_401(client):
    response = await client.post("/invitees/export/listmonk", json={"invitee_uids": ["i1"]})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_export_invitees_as_staff_returns_403(
    client, patch_jwt, jwt_staff, site,
):
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_staff, "staff", site)
        response = await client.post("/invitees/export/listmonk", json={"invitee_uids": ["i1"]})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_export_invitees_as_administrator_returns_403(
    client, patch_jwt, jwt_administrator, site,
):
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_administrator, "administrator", site)
        response = await client.post("/invitees/export/listmonk", json={"invitee_uids": ["i1"]})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_export_invitees_as_superuser_returns_200(
    client, patch_jwt, jwt_superuser, site,
):
    org = FakeOrganization()
    results = [["i1", "invitee1@example.com", "Invitee One"]]
    mocks = _org_mocks(org, results)
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, "superuser", site, mocks)
        response = await client.post("/invitees/export/listmonk", json={"invitee_uids": ["i1"]})
    assert response.status_code == 200
    rows = _read_csv(response.content)
    assert rows[0] == ["email", "name", "attributes"]
    assert rows[1][0] == "invitee1@example.com"
    assert rows[1][1] == "Invitee One"


@pytest.mark.asyncio
async def test_export_invitees_org_not_found_returns_404(
    client, patch_jwt, jwt_superuser, site,
):
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, "superuser", site)
        stack.enter_context(patch(
            "api.routers.listmonk_export.Organization.objects.aget",
            new_callable=AsyncMock,
            side_effect=__import__("facility.models", fromlist=["Organization"]).Organization.DoesNotExist,
        ))
        response = await client.post("/invitees/export/listmonk", json={"invitee_uids": ["i1"]})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_export_invitees_org_without_neomodel_uid_returns_404(
    client, patch_jwt, jwt_superuser, site,
):
    org = FakeOrganization(neomodel_uid=None)
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, "superuser", site, [
            patch("api.routers.listmonk_export.Organization.objects.aget", new_callable=AsyncMock, return_value=org),
        ])
        response = await client.post("/invitees/export/listmonk", json={"invitee_uids": ["i1"]})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_export_invitees_skips_rows_without_email(
    client, patch_jwt, jwt_superuser, site,
):
    org = FakeOrganization()
    results = [
        ["i1", "invitee1@example.com", "Invitee One"],
        ["i2", None, "No Email Invitee"],
    ]
    mocks = _org_mocks(org, results)
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, "superuser", site, mocks)
        response = await client.post("/invitees/export/listmonk", json={"invitee_uids": ["i1", "i2"]})
    assert response.status_code == 200
    rows = _read_csv(response.content)
    assert len(rows) == 2
    assert rows[1][0] == "invitee1@example.com"


@pytest.mark.asyncio
async def test_export_invitees_attributes_json_structure(
    client, patch_jwt, jwt_superuser, site,
):
    import json as jsonlib
    org = FakeOrganization()
    results = [["i1", "invitee1@example.com", "Invitee One"]]
    mocks = _org_mocks(org, results)
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, "superuser", site, mocks)
        response = await client.post("/invitees/export/listmonk", json={"invitee_uids": ["i1"]})
    rows = _read_csv(response.content)
    attributes = jsonlib.loads(rows[1][2])
    assert attributes["pluriproweb"]["user"]["uid"] == "i1"
    assert attributes["pluriproweb"]["user"]["name"] == "Invitee One"
    assert attributes["pluriproweb"]["organization"]["name"] == ORG_NAME
    assert attributes["pluriproweb"]["organization"]["neomodel_uid"] == ENTRY_UID
    assert attributes["pluriproweb"]["organization"]["formatted_name"] == ORG_FORMATTED_NAME


# ===================================================================
# DEDUPLICATION — only one row per email address
# ===================================================================

@pytest.mark.asyncio
async def test_export_invitees_deduplicates_exact_duplicate_emails(
    client, patch_jwt, jwt_superuser, site,
):
    """Two Invitee nodes sharing the exact same email → only one CSV row."""
    org = FakeOrganization()
    results = [
        ["i1", "duplicate@example.com", "First Invitee"],
        ["i2", "duplicate@example.com", "Second Invitee"],
    ]
    mocks = _org_mocks(org, results)
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, "superuser", site, mocks)
        response = await client.post("/invitees/export/listmonk", json={"invitee_uids": ["i1", "i2"]})
    assert response.status_code == 200
    rows = _read_csv(response.content)
    assert len(rows) == 2  # header + exactly one data row
    assert rows[1][0] == "duplicate@example.com"
    assert rows[1][1] == "First Invitee"  # first occurrence wins


@pytest.mark.asyncio
async def test_export_invitees_deduplicates_case_insensitive_emails(
    client, patch_jwt, jwt_superuser, site,
):
    """Emails differing only by case or surrounding whitespace are treated as the same address."""
    org = FakeOrganization()
    results = [
        ["i1", "Someone@Example.com", "First Invitee"],
        ["i2", " someone@example.com ", "Second Invitee"],
        ["i3", "someone@example.com", "Third Invitee"],
    ]
    mocks = _org_mocks(org, results)
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, "superuser", site, mocks)
        response = await client.post("/invitees/export/listmonk", json={"invitee_uids": ["i1", "i2", "i3"]})
    assert response.status_code == 200
    rows = _read_csv(response.content)
    assert len(rows) == 2  # header + exactly one data row
    assert rows[1][1] == "First Invitee"


@pytest.mark.asyncio
async def test_export_invitees_distinct_emails_all_kept(
    client, patch_jwt, jwt_superuser, site,
):
    org = FakeOrganization()
    results = [
        ["i1", "one@example.com", "One"],
        ["i2", "two@example.com", "Two"],
        ["i3", "three@example.com", "Three"],
    ]
    mocks = _org_mocks(org, results)
    with ExitStack() as stack:
        _enter_all(stack, patch_jwt, jwt_superuser, "superuser", site, mocks)
        response = await client.post("/invitees/export/listmonk", json={"invitee_uids": ["i1", "i2", "i3"]})
    assert response.status_code == 200
    rows = _read_csv(response.content)
    assert len(rows) == 4  # header + 3 distinct data rows
    emails = {row[0] for row in rows[1:]}
    assert emails == {"one@example.com", "two@example.com", "three@example.com"}
