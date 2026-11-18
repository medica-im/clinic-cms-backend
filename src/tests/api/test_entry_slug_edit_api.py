"""The HTTP contract of changing an entry's slug.

    GET  /api/v2/entries/{uid}/slug/permission
    GET  /api/v2/entries/{uid}/slug/check?slug=<slug>
    PUT  /api/v2/entries/{uid}/slug   {"slug": "<slug>"}

The rule and the writes are tested against the live graph in test_entry_slug_edit.py.
This file pins what the page relies on: the permission it shows the pen from, the
check its field asks while typing, and refusals as codes it can word.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from directory.entry_slug import EntrySlugRefused

pytestmark = pytest.mark.asyncio

UID = "e" * 32
BASE = f"/api/v2/entries/{UID}/slug"
CHECK = {"slug": "le-mas-association-69", "free": True, "reason": None, "suggestions": ["le-mas-69"]}


@pytest.fixture
def signed_in():
    from main import app
    from api.auth import JWT

    app.dependency_overrides[JWT] = lambda: {"sub": "someone"}
    # Clearing the entries cache looks up the request's Site, which the
    # in-process client has none of; what is cleared is not under test here.
    with patch("api.routers.entry_slugs.clear_cache", AsyncMock()):
        yield
    app.dependency_overrides.pop(JWT, None)


def context(allowed=True):
    return patch(
        "api.routers.entry_slugs.slug_edit_context",
        AsyncMock(return_value=SimpleNamespace(allowed=allowed, caller_uid="u1")),
    )


def service(name, **kwargs):
    return patch(f"api.routers.entry_slugs.{name}", AsyncMock(**kwargs))


async def test_the_permission_says_whether_the_caller_may(versioned_client, signed_in):
    with context(allowed=False):
        response = await versioned_client.get(f"{BASE}/permission")
    assert response.status_code == 200
    assert response.json() == {"allowed": False}


async def test_an_unknown_entry_is_not_found(versioned_client, signed_in):
    with patch("api.routers.entry_slugs.slug_edit_context", AsyncMock(return_value=None)):
        response = await versioned_client.get(f"{BASE}/permission")
    assert response.status_code == 404


async def test_the_check_answers_whether_a_slug_is_free_and_what_else_is(versioned_client, signed_in):
    with context(), service("check_entry_slug", return_value=CHECK) as check:
        response = await versioned_client.get(f"{BASE}/check", params={"slug": "le-mas-association-69"})
    assert response.status_code == 200
    assert response.json() == CHECK
    check.assert_awaited_once_with(UID, "le-mas-association-69")


async def test_someone_who_may_not_change_it_cannot_probe_slugs_either(versioned_client, signed_in):
    with context(allowed=False), service("check_entry_slug") as check:
        response = await versioned_client.get(f"{BASE}/check", params={"slug": "x"})
    assert response.status_code == 403
    check.assert_not_awaited()


async def test_the_change_returns_the_new_slug(versioned_client, signed_in):
    with context(), service("change_entry_slug", return_value="le-mas-association-69") as change:
        response = await versioned_client.put(BASE, json={"slug": "le-mas-association-69"})
    assert response.status_code == 200
    assert response.json() == {"uid": UID, "slug": "le-mas-association-69"}
    change.assert_awaited_once_with(UID, "le-mas-association-69", "u1")


async def test_someone_who_may_not_change_it_is_refused(versioned_client, signed_in):
    with context(allowed=False), service("change_entry_slug") as change:
        response = await versioned_client.put(BASE, json={"slug": "x-69"})
    assert response.status_code == 403
    change.assert_not_awaited()


@pytest.mark.parametrize("code,status", [("taken", 409), ("invalid", 422)])
async def test_a_refusal_is_a_code_the_page_can_word(versioned_client, signed_in, code, status):
    with context(), service("change_entry_slug", side_effect=EntrySlugRefused(code)):
        response = await versioned_client.put(BASE, json={"slug": "x-69"})
    assert response.status_code == status
    assert response.json()["detail"] == {"code": code}
