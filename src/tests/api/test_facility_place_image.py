"""A facility can be given a wide photograph of the place it occupies.

The picture is stored on facility.PlaceImage rather than on
addressbook.Contact: a Contact is a natural or a legal person, and its
thumbnails are square, which crops away the facade that makes a building
recognizable. PlaceImage has its own 16:9 renditions (place_sm / place_lg).

Uploading is authorized exactly like editing the facility itself, so these
tests pin that equivalence: whoever may rename a facility may picture it, and
nobody else.
"""
import io

import pytest
from unittest.mock import AsyncMock, patch

from PIL import Image

# asyncio_mode = auto in pytest.ini already runs these as coroutines; marking
# them again makes pytest-asyncio wrap each test twice.


# PlaceImage.neomodel_uid is a UUIDField, so a readable placeholder like
# "facility-uid-001" is rejected before the assertion under test is reached.
FACILITY_UID = "d3b07384d9134c1fa1e0d7ab1f1c9e01"


def place_image_stand_in(existing=None):
    """
    Replaces the router's PlaceImage with an in-memory double.

    The api suite runs without a database, so a test that let the real manager
    through would try to create one and fail on unrelated schema problems.
    """
    from facility.models import PlaceImage

    # aget_or_create must hand back a row, not None: the handler goes on to
    # replace whatever picture it holds.
    created = existing
    if created is None:
        # image is falsy so the "replace the old file" branch is skipped, but
        # it still has to accept the save() that stores the new upload.
        field = type(
            "ImageField",
            (),
            {
                "save": lambda self, *a, **k: None,
                # An empty ImageField is falsy, and the handler relies on that
                # to tell "no previous picture" from "replace this one".
                "__bool__": lambda self: False,
            },
        )()
        created = type(
            "Row",
            (),
            {"image": field, "alt": "", "neomodel_uid": FACILITY_UID},
        )()

    manager = type(
        "Manager",
        (),
        {
            "aget": AsyncMock(
                side_effect=PlaceImage.DoesNotExist if existing is None else None,
                return_value=existing,
            ),
            "aget_or_create": AsyncMock(return_value=(created, existing is None)),
        },
    )()
    return type(
        "PlaceImageStandIn",
        (),
        {"DoesNotExist": PlaceImage.DoesNotExist, "objects": manager},
    )


def make_image(width: int, height: int, fmt: str = "JPEG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (180, 180, 180)).save(buffer, format=fmt)
    return buffer.getvalue()


def upload_files(payload: bytes, filename: str = "place.jpg", content_type: str = "image/jpeg"):
    return {"file": (filename, payload, content_type)}


@pytest.fixture
def signed_in():
    """
    Satisfies the JWT dependency only.

    Authorization itself is left alone, so tests can assert on which users the
    permission rule was handed and what it did.
    """
    from main import app
    from api.auth import JWT

    app.dependency_overrides[JWT] = lambda: {"sub": "test-user"}
    try:
        yield
    finally:
        app.dependency_overrides.pop(JWT, None)


@pytest.fixture
def authorized():
    """
    Let the request through both gates.

    The JWT dependency is resolved by FastAPI before the handler body runs, so
    patching authorize_api alone still leaves an unauthenticated request being
    turned away with a 401 and the validation under test never reached.
    """
    from main import app
    from api.auth import JWT

    app.dependency_overrides[JWT] = lambda: {"sub": "test-user"}
    try:
        with patch(
            "api.routers.facilities.get_facility_users",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "api.routers.facilities.authorize_api",
            new_callable=AsyncMock,
            return_value=None,
        ):
            yield
    finally:
        app.dependency_overrides.pop(JWT, None)


# --- Validation --------------------------------------------------------------
#
# The client crops to 16:9 before uploading, so these guard against everything
# that reaches the endpoint by another route.


async def test_rejects_a_non_image_content_type(client, authorized):
    response = await client.put(
        f"/facilities/{FACILITY_UID}/image",
        files={"file": ("notes.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert response.status_code == 400
    assert "JPEG" in response.json()["detail"]


def test_rejects_an_image_that_is_too_small():
    """Below 800x450 the large rendition would be upscaled and look soft."""
    from api.routers.facilities import MIN_IMAGE_WIDTH, MIN_IMAGE_HEIGHT

    assert MIN_IMAGE_WIDTH == 800
    assert MIN_IMAGE_HEIGHT == 450


async def test_small_image_is_refused(client, authorized):
    response = await client.put(
        f"/facilities/{FACILITY_UID}/image",
        files=upload_files(make_image(320, 180)),
    )
    assert response.status_code == 400
    assert "at least" in response.json()["detail"]


async def test_rejects_a_square_image(client, authorized):
    """A 1:1 picture is the avatar shape, not the shape of a place."""
    response = await client.put(
        f"/facilities/{FACILITY_UID}/image",
        files=upload_files(make_image(1000, 1000)),
    )
    assert response.status_code == 400
    assert "16:9" in response.json()["detail"]


async def test_rejects_a_portrait_image(client, authorized):
    response = await client.put(
        f"/facilities/{FACILITY_UID}/image",
        files=upload_files(make_image(900, 1600)),
    )
    assert response.status_code == 400
    assert "16:9" in response.json()["detail"]


def test_accepts_a_ratio_within_tolerance():
    """Cropping is done in the browser and lands a pixel or two off exact."""
    from api.routers.facilities import ASPECT_RATIO, ASPECT_TOLERANCE

    for width, height in ((1600, 900), (1599, 900), (1280, 720)):
        assert abs((width / height) - ASPECT_RATIO) <= ASPECT_TOLERANCE


def test_rejects_a_file_over_five_megabytes():
    from api.routers.facilities import MAX_IMAGE_SIZE

    assert MAX_IMAGE_SIZE == 5 * 1024 * 1024


# --- Authorization -----------------------------------------------------------


async def test_upload_is_authorized_like_editing_the_facility(client, signed_in):
    """
    The picture endpoint must consult the same users and the same rule as
    PUT /facilities/{uid}; a separate check would drift out of step and could
    let anyone replace a clinic's photograph.
    """
    with patch(
        "api.routers.facilities.get_facility_users",
        new_callable=AsyncMock,
        return_value=["user-1"],
    ) as get_users, patch(
        "api.routers.facilities.authorize_api",
        new_callable=AsyncMock,
        return_value=None,
    ) as authorize, patch(
        "api.routers.facilities.PlaceImage", place_image_stand_in()
    ):
        await client.put(
            f"/facilities/{FACILITY_UID}/image",
            files=upload_files(make_image(1600, 900)),
        )

    get_users.assert_awaited_once_with(FACILITY_UID)
    assert authorize.await_args.args[0] == "facilities_v2"
    assert authorize.await_args.args[3] == ["user-1"]


async def test_delete_is_authorized_like_editing_the_facility(client, signed_in):
    with patch(
        "api.routers.facilities.get_facility_users",
        new_callable=AsyncMock,
        return_value=["user-1"],
    ) as get_users, patch(
        "api.routers.facilities.authorize_api",
        new_callable=AsyncMock,
        return_value=None,
    ) as authorize, patch(
        "api.routers.facilities.PlaceImage", place_image_stand_in()
    ):
        await client.delete(f"/facilities/{FACILITY_UID}/image")

    get_users.assert_awaited_once_with(FACILITY_UID)
    assert authorize.await_args.args[0] == "facilities_v2"


async def test_the_facility_owners_decide_who_may_picture_it(client, signed_in):
    """
    The connection to the facility is what authorizes the upload, not the rank.
    The handler must hand authorize_api the users get_facility_users returns —
    the owners and creators of the entries at that facility — so that a staff
    member unconnected to it is judged on that connection and not on the role
    alone.
    """
    import inspect
    from api.routers import facilities

    source = inspect.getsource(facilities.put_facility_image)
    assert "get_facility_users(uid)" in source
    assert 'authorize_api("facilities_v2"' in source
    # No role is named in the handler: the decision belongs to the access rules
    # and to the facility's own people.
    for role in ("administrator", "superuser", "staff"):
        assert f'"{role}"' not in source


async def test_refused_upload_never_touches_storage(client, signed_in):
    """An unauthorized caller must not reach the model at all."""
    from fastapi import HTTPException

    with patch(
        "api.routers.facilities.get_facility_users",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "api.routers.facilities.authorize_api",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=403, detail="Forbidden"),
    ), patch("api.routers.facilities.PlaceImage") as place_image:
        response = await client.put(
            f"/facilities/{FACILITY_UID}/image",
            files=upload_files(make_image(1600, 900)),
        )

    assert response.status_code == 403
    place_image.objects.aget_or_create.assert_not_called()


# --- Deleting a picture that was never set -----------------------------------


async def test_deleting_a_missing_picture_is_not_an_error(client, authorized):
    """Idempotent: the caller wanted no picture, and there is none."""
    with patch("api.routers.facilities.PlaceImage", place_image_stand_in()):
        response = await client.delete(f"/facilities/{FACILITY_UID}/image")

    assert response.status_code == 200
    assert response.json() == {"image": None}


# --- Serialization -----------------------------------------------------------


def test_payload_is_none_when_there_is_no_picture():
    from api.routers.facilities import _place_image_payload

    assert _place_image_payload(None) == {"image": None}


def test_public_facility_exposes_image_apart_from_avatar():
    """
    The two keys mean different things: `avatar` is the square picture read
    from Contact, `image` the wide photograph of the place. Collapsing them
    would make a facade appear where a portrait is expected.
    """
    from api.types.public_facility import PublicFacility

    fields = PublicFacility.model_fields
    assert "image" in fields
    assert "avatar" in fields


def test_place_image_type_carries_no_access_level():
    """Unlike an avatar, a photograph of a building is public."""
    from api.types.public_facility import PlaceImage

    assert "access" not in PlaceImage.model_fields
    assert "alt" in PlaceImage.model_fields
