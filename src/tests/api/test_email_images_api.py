"""The HTTP contract of /api/v2/email-images.

The rules -- storage, formats, renaming, deletion, URLs -- are tested in
tests/test_email_images.py against mailer.gallery. This file pins the paths,
the gate (the invitees_v2 rights, as for the templates these images go in),
the shape of an image, and the codes the frontend translates.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mailer.gallery import ImageInvalid, NameTaken
from mailer.models import EmailImage

pytestmark = pytest.mark.asyncio

URL = "/api/v2/email-images"
UID = uuid.uuid4()
URLS = {
    "path": "/media/email_images/o/a.png",
    "url": "https://example.org/annuaire/media/email_images/o/a.png",
    "thumbnail_url": "https://example.org/annuaire/media/email_images/o/a.png.320x320_q85.png",
}


class FakeSite:
    domain = "example.org"


def fake_image(**fields):
    values = dict(uid=UID, name="logo", alt="", width=120, height=40, size=999, created=None)
    values.update(fields)
    # Not a MagicMock: MagicMock(name=...) names the mock, it sets no .name.
    return SimpleNamespace(**values)


@pytest.fixture
def organization():
    return MagicMock(id=7, public_base_url="https://example.org/annuaire", email_template_editor_role="superuser")


@pytest.fixture
def role():
    return "superuser"


@pytest.fixture
def gate(organization, role):
    from main import app
    from api.auth import JWT

    app.dependency_overrides[JWT] = lambda: {"sub": "someone"}
    with (
        patch("api.email_access.get_neo4j_role", AsyncMock(return_value=role)),
        patch(
            "api.email_access.get_site_from_request",
            AsyncMock(return_value=FakeSite()),
        ),
        patch(
            "api.email_access.Organization.objects.aget",
            AsyncMock(return_value=organization),
        ),
        patch("api.routers.email_images.image_urls", MagicMock(return_value=URLS)) as urls,
    ):
        try:
            yield {"image_urls": urls}
        finally:
            app.dependency_overrides.pop(JWT, None)


def service(name, **kwargs):
    return patch(f"api.routers.email_images.{name}", MagicMock(**kwargs))


# --- The gate -----------------------------------------------------------------

WRITES = [("POST", URL), ("PATCH", f"{URL}/{UID}"), ("DELETE", f"{URL}/{UID}")]


def write_kwargs(method):
    if method == "POST":
        return {"files": {"file": ("a.png", b"x", "image/png")}}
    if method == "PATCH":
        return {"json": {"name": "x"}}
    return {}


def all_services():
    from contextlib import ExitStack

    stack = ExitStack()
    mocks = {
        name: stack.enter_context(service(name, **kwargs))
        for name, kwargs in {
            "list_images": {"return_value": []},
            "add_image": {"return_value": fake_image()},
            "update_image": {"return_value": fake_image()},
            "delete_image": {},
        }.items()
    }
    return stack, mocks


@pytest.mark.parametrize("role", ["staff", "registered", None])
@pytest.mark.parametrize("method, path", [("GET", URL)] + WRITES)
async def test_below_administrator_every_route_is_refused(versioned_client, gate, method, path):
    stack, mocks = all_services()
    with stack:
        response = await versioned_client.request(method, path, **write_kwargs(method))

    assert response.status_code == 403
    assert not any(mock.called for mock in mocks.values())


@pytest.mark.parametrize("role", ["administrator"])
async def test_an_administrator_may_see_the_images_superusers_manage(versioned_client, gate):
    stack, _ = all_services()
    with stack:
        response = await versioned_client.get(URL)

    assert response.status_code == 200


@pytest.mark.parametrize("role", ["administrator"])
@pytest.mark.parametrize("method, path", WRITES)
async def test_an_administrator_changes_no_image_when_superusers_manage_them(versioned_client, gate, method, path):
    stack, mocks = all_services()
    with stack:
        response = await versioned_client.request(method, path, **write_kwargs(method))

    assert response.status_code == 403
    assert response.json()["detail"] == {"code": "not_editor"}
    assert not any(mocks[n].called for n in ("add_image", "update_image", "delete_image"))


@pytest.mark.parametrize("role", ["administrator"])
@pytest.mark.parametrize("method, path", WRITES)
async def test_an_administrator_may_manage_images_when_the_organization_lets_them(
    versioned_client, gate, organization, method, path
):
    organization.email_template_editor_role = "administrator"
    stack, _ = all_services()
    with stack:
        response = await versioned_client.request(method, path, **write_kwargs(method))

    assert response.status_code in (200, 201, 204)


# --- Listing ------------------------------------------------------------------


async def test_the_list_gives_each_image_its_urls_from_the_sites_public_url(
    versioned_client, gate, organization
):
    with service("list_images", return_value=[fake_image()]) as list_images:
        response = await versioned_client.get(URL)

    assert response.status_code == 200
    assert response.json() == [
        {
            "uid": str(UID),
            "name": "logo",
            "alt": "",
            "width": 120,
            "height": 40,
            "size": 999,
            "created": None,
            **URLS,
        }
    ]
    assert list_images.call_args.args == (organization,)
    assert gate["image_urls"].call_args.args[1] == "https://example.org/annuaire"


# --- Uploading ----------------------------------------------------------------


async def test_an_upload_hands_the_bytes_to_the_gallery(versioned_client, gate, organization):
    with service("add_image", return_value=fake_image()) as add:
        response = await versioned_client.post(
            URL,
            files={"file": ("logo.png", b"bytes", "image/png")},
            data={"name": "Logo", "alt": "Le logo"},
        )

    assert response.status_code == 201
    assert response.json()["url"] == URLS["url"]
    assert add.call_args.args == (organization, "logo.png", b"bytes")
    assert add.call_args.kwargs == {"name": "Logo", "alt": "Le logo"}


@pytest.mark.parametrize("code", ["too_large", "unsupported_type", "not_an_image"])
async def test_a_refused_upload_is_a_422_with_its_code(versioned_client, gate, code):
    with service("add_image", side_effect=ImageInvalid(code)):
        response = await versioned_client.post(URL, files={"file": ("a.png", b"x", "image/png")})

    assert response.status_code == 422
    assert response.json()["detail"] == {"code": code}


# --- Renaming -----------------------------------------------------------------


async def test_a_rename_answers_the_image(versioned_client, gate, organization):
    with service("update_image", return_value=fake_image(name="Logo")) as update:
        response = await versioned_client.patch(f"{URL}/{UID}", json={"name": "Logo"})

    assert response.status_code == 200
    assert response.json()["name"] == "Logo"
    assert update.call_args.args == (organization, UID)
    assert update.call_args.kwargs == {"name": "Logo", "alt": None}


async def test_a_name_already_used_is_a_409(versioned_client, gate):
    with service("update_image", side_effect=NameTaken("logo")):
        response = await versioned_client.patch(f"{URL}/{UID}", json={"name": "logo"})

    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "name_taken"}


async def test_an_empty_name_is_a_422(versioned_client, gate):
    with service("update_image", side_effect=ImageInvalid("name_required")):
        response = await versioned_client.patch(f"{URL}/{UID}", json={"name": " "})

    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "name_required"}


# --- Deleting -----------------------------------------------------------------


async def test_a_deletion_answers_204(versioned_client, gate, organization):
    with service("delete_image") as delete:
        response = await versioned_client.delete(f"{URL}/{UID}")

    assert response.status_code == 204
    assert delete.call_args.args == (organization, UID)


@pytest.mark.parametrize(
    "method, name, kwargs",
    [("PATCH", "update_image", {"json": {"name": "x"}}), ("DELETE", "delete_image", {})],
)
async def test_an_image_not_in_this_organization_is_not_found(versioned_client, gate, method, name, kwargs):
    with service(name, side_effect=EmailImage.DoesNotExist):
        response = await versioned_client.request(method, f"{URL}/{UID}", **kwargs)

    assert response.status_code == 404


async def test_a_malformed_uid_is_not_found_rather_than_a_crash(versioned_client, gate):
    response = await versioned_client.delete(f"{URL}/not-a-uid")

    assert response.status_code in (404, 422)
