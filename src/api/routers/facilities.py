import os
import logging
from io import BytesIO
from typing import Annotated, Union
from fastapi import APIRouter, status, Depends, Request, HTTPException, UploadFile, File, Form
from PIL import Image
from pydantic import BaseModel
from asgiref.sync import sync_to_async
from django.core.files.uploadedfile import InMemoryUploadedFile
from api.serializers.facility import async_get_facilities, async_get_facility, create_facility, update_facility, delete_facility
from api.types.facility import Facility, FacilityPost, FacilityPut
from api.auth import authorize_api, may_authorize_api, verify_user_access, JWT
from api.neo4j_auth import get_neo4j_role, normalize_neo4j_role
from api.utils import get_site_from_request
from facility.models import Organization, PlaceImage
from directory.models.agraph import Facility as AgraphFacility

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/facilities")
async def facilities(request: Request, jwt: Annotated[dict, Depends(JWT)]) -> list[Facility]:
    site = await get_site_from_request(request)
    raw_role = await get_neo4j_role(jwt, site) or "anonymous"
    role = normalize_neo4j_role(raw_role)
    if role not in ("staff", "administrator", "superuser"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff role or higher required"
        )
    if role == "superuser":
        return await async_get_facilities()
    # staff / administrator: return only facilities from this organization
    org = await Organization.objects.aget(site=site)
    if not org.neomodel_uid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization has no linked Entry"
        )
    entry_uid = org.neomodel_uid.hex
    await verify_user_access(jwt, entry_uid)
    return await async_get_facilities(entry_uid=entry_uid)

@router.get("/facilities/{uid}")
async def facility(uid: str) -> Facility:
    return await async_get_facility(uid=uid)

@router.get("/facilities-slug/{slug}")
async def facility_by_slug(slug: str) -> Facility:
    return await async_get_facility(slug=slug)

@router.post("/facilities/", status_code=status.HTTP_201_CREATED)
async def post_facility(facility: FacilityPost, request: Request, jwt: Annotated[dict, Depends(JWT)]) -> Facility:
    logger.debug(f'${facility=}')
    await authorize_api("facilities_v2", request, jwt)
    return await create_facility(facility, request, jwt)

async def get_facility_users(uid: str):
    """
    The people who answer for this facility.

    Being staff of the organisation is not enough — a facility is answered for
    by those attached to it, or nobody could stop one member of a large site
    from editing a practice they have nothing to do with. That means:

      * whoever owns or created the facility itself, and
      * whoever owns or created an entry located at it.

    Owners and creators are gathered together rather than one falling back on
    the other: an entry with an owner still leaves its creator answerable.
    """
    try:
        facility_node = await AgraphFacility.nodes.get(uid=uid)
    except AgraphFacility.DoesNotExist:
        raise HTTPException(status_code=404, detail="Facility not found")

    users = []
    users.extend(await facility_node.owner.all())
    users.extend(await facility_node.creator.all())
    for entry_node in await facility_node.entries.all():
        users.extend(await entry_node.owner.all())
        users.extend(await entry_node.creator.all())

    # The same person can be reached by several of those paths.
    unique = {}
    for user in users:
        unique[user.element_id] = user
    return list(unique.values())

@router.put("/facilities/{uid}", status_code=status.HTTP_201_CREATED)
async def put_facility(uid: str, facility: FacilityPut, request: Request, jwt: Annotated[dict, Depends(JWT)]) -> Facility:
    users = await get_facility_users(uid)
    await authorize_api("facilities_v2", request, jwt, users)
    return await update_facility(uid, facility, request)

@router.delete("/facilities/{uid}")
async def delete(uid: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    users = await get_facility_users(uid)
    await authorize_api("facilities_v2", request, jwt, users)
    return await delete_facility(uid)


# --- Place picture -----------------------------------------------------------
#
# Authorized exactly like editing the facility itself (get_facility_users +
# "facilities_v2"), so whoever may rename a facility may also picture it, and
# there is no second permission rule to drift out of step.

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
# 16:9 at the size the large rendition needs; the client crops to ratio before
# uploading, so this only has to reject images too small to render well.
MIN_IMAGE_WIDTH = 800
MIN_IMAGE_HEIGHT = 450
# Cropping is done client-side, so anything noticeably off 16:9 got here by
# another route and would be cropped again by the thumbnailer.
ASPECT_RATIO = 16 / 9
ASPECT_TOLERANCE = 0.05


def _place_image_payload(place: PlaceImage | None) -> dict:
    """The picture's renditions, shaped like the avatar payload."""
    if place is None or not place.image:
        return {"image": None}

    def url(alias):
        try:
            return place.image[alias].url
        except Exception as e:
            logger.error(f"place image {alias} error: {e}")
            return None

    return {
        "image": {
            "sm": url("place_sm"),
            "lg": url("place_lg"),
            "raw": place.image.url,
            "alt": place.alt,
        }
    }


@router.put("/facilities/{uid}/image", status_code=status.HTTP_200_OK)
async def put_facility_image(
    uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
    file: UploadFile = File(...),
    alt: str = Form(""),
):
    users = await get_facility_users(uid)
    await authorize_api("facilities_v2", request, jwt, users)

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="File must be JPEG, PNG, or WebP",
        )

    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")

    try:
        img = Image.open(BytesIO(contents))
        width, height = img.size
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image file")

    if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Image must be at least {MIN_IMAGE_WIDTH}x{MIN_IMAGE_HEIGHT} pixels"
            ),
        )

    if abs((width / height) - ASPECT_RATIO) > ASPECT_TOLERANCE:
        raise HTTPException(
            status_code=400,
            detail="Image must be in 16:9 format",
        )

    place, _ = await PlaceImage.objects.aget_or_create(neomodel_uid=uid)

    # Drop the previous file and its renditions, or they linger on disk under
    # names the thumbnailer will never look up again.
    if place.image:
        try:
            from easy_thumbnails.files import get_thumbnailer
            thumbnailer = await sync_to_async(get_thumbnailer)(place.image)
            await sync_to_async(thumbnailer.delete_thumbnails)()
        except Exception as e:
            logger.warning(f"Could not delete old thumbnails: {e}")
        await sync_to_async(place.image.delete)(save=False)

    ext = (file.filename or "place.jpg").rsplit(".", 1)[-1].lower()
    upload = InMemoryUploadedFile(
        BytesIO(contents),
        field_name="image",
        name=f"{uid}.{ext}",
        content_type=file.content_type,
        size=len(contents),
        charset=None,
    )
    place.alt = alt
    await sync_to_async(place.image.save)(upload.name, upload, save=True)

    return _place_image_payload(place)


@router.get("/facilities/{uid}/can-edit", status_code=status.HTTP_200_OK)
async def can_edit_facility(
    uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
) -> dict:
    """
    Whether the caller may change this facility.

    The frontend cannot work this out: it knows the user's role but not which
    facilities they are connected to, so without this it can only ask "is
    anybody signed in?" and offers the editing controls to every visitor with an
    account — including staff with no connection to the facility, who are then
    refused by the server when they try to save.

    Deliberately its own endpoint rather than a field on /public/facilities:
    that payload is cached per site with no user in the key, so a per-user flag
    stored there would be served to whoever asked next.

    Answered by may_authorize_api — the same rule the write endpoints enforce,
    asked as a question rather than caught as an exception, so the button and
    the server can never disagree and a broken permission table is not mistaken
    for a user who simply lacks rights.
    """
    users = await get_facility_users(uid)
    allowed = await may_authorize_api("facilities_v2", request, jwt, users, method="PUT")
    return {"can_edit": allowed}


class PlaceImageAlt(BaseModel):
    alt: str = ""


@router.patch("/facilities/{uid}/image", status_code=status.HTTP_200_OK)
async def patch_facility_image_alt(
    uid: str,
    payload: PlaceImageAlt,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    """
    Corrects the description of an existing picture, leaving the file alone.

    Separate from the PUT: that one requires a file, so without this a caller
    wanting to describe a picture would have to find and upload the original
    again. Pictures moved over from the old storage all arrived without a
    description, which is exactly the case this serves.
    """
    users = await get_facility_users(uid)
    await authorize_api("facilities_v2", request, jwt, users)

    try:
        place = await PlaceImage.objects.aget(neomodel_uid=uid)
    except PlaceImage.DoesNotExist:
        raise HTTPException(status_code=404, detail="This facility has no picture")

    place.alt = payload.alt
    await sync_to_async(place.save)()
    return _place_image_payload(place)


@router.delete("/facilities/{uid}/image", status_code=status.HTTP_200_OK)
async def delete_facility_image(
    uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    users = await get_facility_users(uid)
    await authorize_api("facilities_v2", request, jwt, users)

    try:
        place = await PlaceImage.objects.aget(neomodel_uid=uid)
    except PlaceImage.DoesNotExist:
        return {"image": None}

    if place.image:
        try:
            from easy_thumbnails.files import get_thumbnailer
            thumbnailer = await sync_to_async(get_thumbnailer)(place.image)
            await sync_to_async(thumbnailer.delete_thumbnails)()
        except Exception as e:
            logger.warning(f"Could not delete old thumbnails: {e}")
        await sync_to_async(place.image.delete)(save=False)

    await sync_to_async(place.delete)()
    return {"image": None}