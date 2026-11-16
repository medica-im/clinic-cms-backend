"""The HTTP contract of the quality controls.

    GET /api/v2/entries/{uid}/quality         what one entry is missing: its owner or creator,
                                              administrators and superusers
    GET /api/v2/directories/{name}/quality    the whole directory, by rule: administrators and
                                              superusers

Nothing is cached, and nothing here blocks a save: the answers are lists of codes the pages word.
What the rules are, and how the facts are gathered, are tested in test_quality.py and
test_quality_facts.py; this file pins who may ask, and the shape the pages read.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio

UID = "e" * 32


@pytest.fixture
def signed_in():
    from main import app
    from api.auth import JWT

    app.dependency_overrides[JWT] = lambda: {"sub": "someone"}
    yield
    app.dependency_overrides.pop(JWT, None)


def caller(role, connected=False):
    return patch(
        "api.routers.quality.quality_caller",
        AsyncMock(return_value=SimpleNamespace(role=role, connected=connected, site=object())),
    )


def of_site(answer=True):
    return patch("api.routers.quality.directory_is_of_site", AsyncMock(return_value=answer))


def facts(**changes):
    from directory.quality import EntryFacts

    base = dict(uid=UID, slug="x", name="X", label="X", type_slug="ligne-ecoute", immaterial=True, nature="service",
                listed=True, active=True, description=None, offers=None, who_can_contact=None, care_levels=None,
                siren=None, has_porteur=True, coverage=1, schedules=[], has_location=False)
    return EntryFacts(**{**base, **changes})


async def test_an_owner_or_creator_reads_what_their_entry_is_missing(versioned_client, signed_in):
    with caller("staff", connected=True), patch(
        "api.routers.quality.entry_facts", AsyncMock(return_value=facts())
    ):
        response = await versioned_client.get(f"/entries/{UID}/quality")
    assert response.status_code == 200
    body = response.json()
    assert {"code": "line_without_phone", "severity": "missing"} in body
    assert {"code": "no_description", "severity": "incomplete"} in body
    assert [item["severity"] for item in body] == sorted((item["severity"] for item in body), key=("missing", "incomplete").index)


@pytest.mark.parametrize("role", ["administrator", "superuser"])
async def test_administrators_and_superusers_read_any_entry(versioned_client, signed_in, role):
    with caller(role), patch("api.routers.quality.entry_facts", AsyncMock(return_value=facts())):
        response = await versioned_client.get(f"/entries/{UID}/quality")
    assert response.status_code == 200


@pytest.mark.parametrize("role", ["staff", "registered", "anonymous", None])
async def test_someone_who_is_neither_connected_to_the_entry_nor_an_administrator_is_refused(versioned_client, signed_in, role):
    with caller(role), patch("api.routers.quality.entry_facts", AsyncMock(return_value=facts())):
        response = await versioned_client.get(f"/entries/{UID}/quality")
    assert response.status_code == 403


async def test_an_unknown_entry_is_a_404(versioned_client, signed_in):
    with caller("superuser"), patch("api.routers.quality.entry_facts", AsyncMock(return_value=None)):
        response = await versioned_client.get(f"/entries/{UID}/quality")
    assert response.status_code == 404


async def test_the_directory_report_is_for_administrators_and_superusers(versioned_client, signed_in):
    report = [{"code": "no_contact", "severity": "missing", "entries": [{"uid": UID, "slug": "x", "name": "X", "label": "X", "type": "ligne d'écoute"}]}]
    with caller("administrator"), of_site(), patch("api.routers.quality.directory_report", AsyncMock(return_value=report)):
        allowed = await versioned_client.get("/directories/sm/quality")
    assert allowed.status_code == 200
    assert allowed.json() == report
    for role in ("staff", "registered", None):
        with caller(role, connected=True), of_site(), patch("api.routers.quality.directory_report", AsyncMock(return_value=report)):
            assert (await versioned_client.get("/directories/sm/quality")).status_code == 403


async def test_an_administrator_reads_the_directories_of_their_site_not_another_sites(versioned_client, signed_in):
    with caller("administrator"), of_site(False), patch("api.routers.quality.directory_report", AsyncMock(return_value=[])) as report:
        response = await versioned_client.get("/directories/elsewhere/quality")
    assert response.status_code == 403
    report.assert_not_called()
