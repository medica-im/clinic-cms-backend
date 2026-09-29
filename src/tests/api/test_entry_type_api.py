"""The HTTP contract of changing an entry's effector type.

    GET  /api/v2/entries/{uid}/effector-type/permission
    GET  /api/v2/entries/{uid}/effector-type/preview?effector_type=<uid>
    PUT  /api/v2/entries/{uid}/effector-type   {"effector_type": "<uid>"}

The rule (who, until when) is tested in tests/test_entry_type_edit.py; the
write itself -- one transaction, shape checked on both sides -- against the
live graph in tests/test_entry_type_change.py. This file pins what the page
relies on: the permission it shows the pen from, the tags it warns about,
and refusals as codes it can word.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.serializers.entry_type import EntryTypeRefused
from directory.entry_type_edit import TypeEditPermission

pytestmark = pytest.mark.asyncio

UID = "e" * 32
TYPE = "t" * 32
BASE = f"/api/v2/entries/{UID}/effector-type"
DEADLINE = datetime(2026, 10, 29, tzinfo=timezone.utc)


def context(allowed=True, reason=None):
    return SimpleNamespace(
        uid=UID,
        slug="dupont-jean-mg-69",
        type_uid="old" + "0" * 29,
        created_at_ms=1790000000000,
        caller_uid="u1",
        permission=TypeEditPermission(allowed, reason, 30 if reason != "not_allowed" else None, DEADLINE),
    )


@pytest.fixture
def signed_in():
    from main import app
    from api.auth import JWT

    app.dependency_overrides[JWT] = lambda: {"sub": "someone"}
    # Clearing the entries cache looks up the request's Site, which the
    # in-process client has none of; what is cleared is not under test here.
    with patch("api.routers.entry_type.clear_cache", AsyncMock()):
        yield
    app.dependency_overrides.pop(JWT, None)


def service(name, **kwargs):
    return patch(f"api.routers.entry_type.{name}", AsyncMock(**kwargs))


# --- Permission --------------------------------------------------------------------


async def test_the_permission_says_whether_and_until_when(versioned_client, signed_in):
    with service("type_edit_context", return_value=context()):
        response = await versioned_client.get(f"{BASE}/permission")

    assert response.status_code == 200
    assert response.json() == {
        "allowed": True,
        "reason": None,
        "window_days": 30,
        "deadline": "2026-10-29T00:00:00Z",
        "created_at": 1790000000000,
    }


async def test_an_expired_window_is_said_with_its_length(versioned_client, signed_in):
    with service("type_edit_context", return_value=context(False, "expired")):
        response = await versioned_client.get(f"{BASE}/permission")

    assert response.json()["allowed"] is False
    assert response.json()["reason"] == "expired"
    assert response.json()["window_days"] == 30


async def test_an_unknown_entry_is_not_found(versioned_client, signed_in):
    with service("type_edit_context", return_value=None):
        response = await versioned_client.get(f"{BASE}/permission")

    assert response.status_code == 404


async def test_signed_out_is_refused(versioned_client):
    response = await versioned_client.get(f"{BASE}/permission")

    assert response.status_code == 401


# --- Preview -----------------------------------------------------------------------


async def test_the_preview_lists_the_tags_that_would_go(versioned_client, signed_in):
    tags = [{"uid": "g1", "label": "Mention IPA"}]
    with (
        service("type_edit_context", return_value=context()),
        service("preview_removed_tags", return_value=tags) as preview,
    ):
        response = await versioned_client.get(f"{BASE}/preview", params={"effector_type": TYPE})

    assert response.status_code == 200
    assert response.json() == {"removed_tags": tags}
    assert preview.await_args.args == (UID, TYPE)


async def test_the_preview_is_for_those_who_may_change_it(versioned_client, signed_in):
    with (
        service("type_edit_context", return_value=context(False, "not_allowed")),
        service("preview_removed_tags") as preview,
    ):
        response = await versioned_client.get(f"{BASE}/preview", params={"effector_type": TYPE})

    assert response.status_code == 403
    preview.assert_not_awaited()


# --- The change --------------------------------------------------------------------


async def test_the_change_answers_the_new_slug(versioned_client, signed_in):
    result = {"uid": UID, "slug": "dupont-jean-ipa-69", "removed_tags": []}
    with (
        service("type_edit_context", return_value=context()),
        service("change_entry_type", return_value=result) as change,
    ):
        response = await versioned_client.put(BASE, json={"effector_type": TYPE})

    assert response.status_code == 200
    assert response.json() == result
    assert change.await_args.args[1] == TYPE


@pytest.mark.parametrize("reason", ["not_allowed", "expired", "no_date"])
async def test_a_caller_without_the_right_changes_nothing(versioned_client, signed_in, reason):
    with (
        service("type_edit_context", return_value=context(False, reason)),
        service("change_entry_type") as change,
    ):
        response = await versioned_client.put(BASE, json={"effector_type": TYPE})

    assert response.status_code == 403
    assert response.json()["detail"] == {"code": reason}
    change.assert_not_awaited()


@pytest.mark.parametrize(
    "refusal, status",
    [
        (EntryTypeRefused("same_type"), 409),
        (EntryTypeRefused("duplicate", slug="dupont-jean-ipa-69"), 409),
        (EntryTypeRefused("malformed", problems=["HAS_EFFECTOR_TYPE:2"]), 409),
        (EntryTypeRefused("unknown_type"), 422),
    ],
    ids=["same_type", "duplicate", "malformed", "unknown_type"],
)
async def test_a_refused_change_is_a_code(versioned_client, signed_in, refusal, status):
    with (
        service("type_edit_context", return_value=context()),
        service("change_entry_type", side_effect=refusal),
    ):
        response = await versioned_client.put(BASE, json={"effector_type": TYPE})

    assert response.status_code == status
    assert response.json()["detail"]["code"] == refusal.code
    if refusal.code == "duplicate":
        assert response.json()["detail"]["slug"] == "dupont-jean-ipa-69"
    if refusal.code == "malformed":
        assert response.json()["detail"]["problems"] == ["HAS_EFFECTOR_TYPE:2"]
