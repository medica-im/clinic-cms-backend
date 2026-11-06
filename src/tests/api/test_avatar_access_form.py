"""PUT /entries/{uid}/avatar: the access form field travels with the picture.

The upload modal always sends it. Pinned because FastAPI 0.147-0.162 reworked
how omitted and empty form fields are read: a chosen level must be stored as
sent, and an omitted one must take the declared default, not be refused.
"""
import pytest
from unittest.mock import AsyncMock, patch

from tests.api.test_avatar_filename import (  # noqa: F401 - authorized is a fixture
    ENTRY_UID,
    RecordingImageField,
    authorized,
    contact_stand_in,
    entry_node_stand_in,
    make_image,
    upload_files,
)


async def upload(client, data):
    stand_in, row = contact_stand_in(RecordingImageField())
    row.avatar_access = "staff"
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
        response = await client.put(
            f"/entries/{ENTRY_UID}/avatar",
            files=upload_files(make_image(600, 600)),
            data=data,
        )
    return response, row


async def test_the_chosen_level_is_stored(client, authorized):
    response, row = await upload(client, {"access": "administrator"})
    assert response.status_code == 200, response.text
    assert row.avatar_access == "administrator"


async def test_an_omitted_level_takes_the_default(client, authorized):
    response, row = await upload(client, {})
    assert response.status_code == 200, response.text
    assert row.avatar_access == "anonymous"
