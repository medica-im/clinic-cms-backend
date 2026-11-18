"""Replacing an avatar must not reuse the filename of the picture it replaces.

The handler pinned the stored name to ``f"{uid}.{ext}"``, so every upload for an
entry wrote to the same path. The URL the API returns was therefore identical
before and after a replacement, while the bytes behind it changed — the one
combination HTTP caching cannot cope with. The browser kept showing the previous
face until a manual reload, which read on the frontend as a missing reload
signal when the data had in fact been refetched correctly.

Letting the name differ per upload makes the stale picture impossible rather
than something the client has to work around with cache-busting query strings.

This is not versioning: the previous file and its thumbnails are still deleted
on replacement, so an entry keeps exactly one picture. Only the *name* of that
one picture changes.
"""
import io

import pytest
from unittest.mock import AsyncMock, patch

from PIL import Image


# Contact.neomodel_uid is a UUIDField, so a readable placeholder is rejected
# long before the assertion under test is reached.
ENTRY_UID = "a1b2c3d4e5f6478899aabbccddeeff00"


def make_image(width: int, height: int, fmt: str = "JPEG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (180, 180, 180)).save(buffer, format=fmt)
    return buffer.getvalue()


def upload_files(payload: bytes, filename: str = "avatar.jpg"):
    return {"file": (filename, payload, "image/jpeg")}


class RecordingImageField:
    """
    Stands in for the ImageField, remembering what name it was handed.

    The api suite runs without a database, so the real field cannot be used:
    what these tests need is only the name the handler chose, and whether it
    asked storage to remove the previous file.
    """

    def __init__(self, existing_name=""):
        self.name = existing_name
        self.assigned_names = []
        self.deleted_names = []

    def __bool__(self):
        # Truthy only when the row already holds a picture, which is how the
        # handler tells "replace this" from "there was nothing here".
        return bool(self.name)

    def delete(self, save=True):
        # What actually removes the bytes from storage. Recorded because a
        # picture the user replaced or removed must not survive on disk.
        if self.name:
            self.deleted_names.append(self.name)
        self.name = ""


def contact_stand_in(field):
    row = type(
        "Row",
        (),
        {"profile_image": field, "avatar_access": "anonymous", "neomodel_uid": ENTRY_UID},
    )()

    async def asave():
        # The handler assigns an uploaded file to profile_image; record the
        # name it carried at save time.
        value = row.profile_image
        name = getattr(value, "name", None)
        if name:
            field.assigned_names.append(name)
        return None

    row.asave = asave

    manager = type(
        "Manager",
        (),
        {"aget_or_create": AsyncMock(return_value=(row, False))},
    )()
    return type("ContactStandIn", (), {"objects": manager}), row


@pytest.fixture
def authorized():
    from main import app
    from api.auth import JWT

    app.dependency_overrides[JWT] = lambda: {"sub": "test-user"}
    try:
        with patch(
            "api.routers.avatar.authorize_api",
            new_callable=AsyncMock,
            return_value=None,
        ):
            yield
    finally:
        app.dependency_overrides.pop(JWT, None)


def entry_node_stand_in():
    """The graph node the handler reads owners and creators from."""
    return type(
        "Node",
        (),
        {
            "owner": type("R", (), {"all": AsyncMock(return_value=[])})(),
            "creator": type("R", (), {"all": AsyncMock(return_value=[])})(),
        },
    )()


async def upload(client, field, filename="avatar.jpg"):
    """Runs one upload through the handler against the recording field."""
    stand_in, row = contact_stand_in(field)
    with patch("api.routers.avatar.Contact", stand_in), patch(
        "api.routers.avatar.AgraphEntry"
    ) as entry_cls, patch(
        "api.routers.avatar.async_get_avatar_url",
        new_callable=AsyncMock,
        return_value={"sm": "", "lg": "", "raw": ""},
    ), patch(
        "api.routers.avatar.clear_cache", new_callable=AsyncMock, return_value=None
    ):
        entry_cls.nodes.get = AsyncMock(return_value=entry_node_stand_in())
        return await client.put(
            f"/entries/{ENTRY_UID}/avatar",
            files=upload_files(make_image(600, 600), filename),
            data={"access": "anonymous"},
        )


async def test_two_uploads_do_not_reuse_the_same_filename(client, authorized):
    """The rule: a replacement is stored under a name of its own.

    Same entry, same extension, same everything a caller controls — and still a
    different stored name, because that is what makes the URL change.
    """
    field = RecordingImageField()
    await upload(client, field)
    await upload(client, field)

    assert len(field.assigned_names) == 2, field.assigned_names
    first, second = field.assigned_names
    assert first != second, (
        "both uploads were stored under the same name, so the URL cannot change"
    )


async def test_the_stored_name_still_identifies_the_entry(client, authorized):
    """The uid stays in the name, so a file on disk is still traceable."""
    field = RecordingImageField()
    await upload(client, field)

    assert field.assigned_names, "nothing was stored"
    assert ENTRY_UID in field.assigned_names[0]


async def test_the_extension_follows_the_uploaded_type(client, authorized):
    field = RecordingImageField()
    await upload(client, field, filename="portrait.png")

    assert field.assigned_names[0].endswith(".png"), field.assigned_names


# --- Privacy -----------------------------------------------------------------
#
# A photograph of a person is kept only while that person's entry is meant to
# show one. Giving each upload its own name makes this load-bearing: with a
# fixed name a replacement overwrote the previous file whether or not the code
# deleted it, so a missed deletion was invisible. Now a file that is not deleted
# simply stays on disk, readable by anyone who knows the URL.


async def test_replacing_a_picture_removes_the_previous_file(client, authorized):
    """The old photograph is taken off storage, not merely unreferenced."""
    field = RecordingImageField(existing_name="avatars/old-picture.jpg")
    await upload(client, field)

    assert "avatars/old-picture.jpg" in field.deleted_names, (
        "the replaced photograph was left on disk"
    )


async def test_deleting_the_avatar_removes_the_file(client, authorized):
    """Asking for the picture to go must remove the bytes, not just the link."""
    field = RecordingImageField(existing_name="avatars/unwanted.jpg")
    stand_in, row = contact_stand_in(field)

    async def aget(**kwargs):
        return row

    stand_in.objects.aget = aget

    with patch("api.routers.avatar.Contact", stand_in), patch(
        "api.routers.avatar.clear_cache", new_callable=AsyncMock, return_value=None
    ), patch(
        "api.routers.avatar.AgraphEntry"
    ) as entry_cls:
        node = type(
            "Node",
            (),
            {
                "owner": type("R", (), {"all": AsyncMock(return_value=[])})(),
                "creator": type("R", (), {"all": AsyncMock(return_value=[])})(),
            },
        )()
        entry_cls.nodes.get = AsyncMock(return_value=node)
        response = await client.delete(f"/entries/{ENTRY_UID}/avatar")

    assert response.status_code == 200, response.text
    assert "avatars/unwanted.jpg" in field.deleted_names, (
        "the removed photograph was left on disk"
    )
