import logging
from typing import Annotated
from io import BytesIO
from fastapi import APIRouter, status, Request, Depends, HTTPException, UploadFile, File
from PIL import Image
from asgiref.sync import sync_to_async
from django.core.files.uploadedfile import InMemoryUploadedFile
from api.auth import authorize_api, JWT
from addressbook.models import Contact
from directory.models.agraph import Entry as AgraphEntry
from api.utils import clear_cache
from directory.utils import async_get_avatar_url

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MIN_DIMENSION = 500


@router.put(
    "/entries/{uid}/avatar",
    status_code=status.HTTP_200_OK,
)
async def upload_avatar(
    uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
    file: UploadFile = File(...),
):
    # Lookup entry and authorize
    try:
        entry_node = await AgraphEntry.nodes.get(uid=uid)
    except AgraphEntry.DoesNotExist:
        raise HTTPException(status_code=404, detail="Entry not found")
    users = await entry_node.owner.all() or await entry_node.creator.all()
    await authorize_api("entries_v2", request, jwt, users)

    # Validate file type
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail="File must be JPEG, PNG, or WebP",
        )

    # Read file contents
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail="File too large (max 5MB)",
        )

    # Validate image dimensions
    try:
        img = Image.open(BytesIO(contents))
        width, height = img.size
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image file")
    if width < MIN_DIMENSION or height < MIN_DIMENSION:
        raise HTTPException(
            status_code=400,
            detail=f"Image must be at least {MIN_DIMENSION}x{MIN_DIMENSION} pixels",
        )

    # Get or create Contact for this entry
    contact, _ = await Contact.objects.aget_or_create(neomodel_uid=uid)

    # Delete old image and its thumbnails if exists
    if contact.profile_image:
        try:
            from easy_thumbnails.files import get_thumbnailer
            thumbnailer = await sync_to_async(get_thumbnailer)(contact.profile_image)
            await sync_to_async(thumbnailer.delete_thumbnails)()
        except Exception as e:
            logger.warning(f"Could not delete old thumbnails: {e}")
        await sync_to_async(contact.profile_image.delete)(save=False)

    # Create Django InMemoryUploadedFile from bytes
    ext = (file.filename or "avatar.jpg").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"
    filename = f"{uid}.{ext}"

    django_file = InMemoryUploadedFile(
        file=BytesIO(contents),
        field_name="profile_image",
        name=filename,
        content_type=file.content_type,
        size=len(contents),
        charset=None,
    )
    contact.profile_image = django_file
    await contact.asave()

    # Return updated avatar URLs
    await clear_cache("v2:entries", request)
    avatar = await async_get_avatar_url(entry=entry_node)
    return {"avatar": avatar}


@router.delete(
    "/entries/{uid}/avatar",
    status_code=status.HTTP_200_OK,
)
async def delete_avatar(
    uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    # Lookup entry and authorize
    try:
        entry_node = await AgraphEntry.nodes.get(uid=uid)
    except AgraphEntry.DoesNotExist:
        raise HTTPException(status_code=404, detail="Entry not found")
    users = await entry_node.owner.all() or await entry_node.creator.all()
    await authorize_api("entries_v2", request, jwt, users)

    try:
        contact = await Contact.objects.aget(neomodel_uid=uid)
    except Contact.DoesNotExist:
        raise HTTPException(status_code=404, detail="Contact not found")

    if contact.profile_image:
        try:
            from easy_thumbnails.files import get_thumbnailer
            thumbnailer = await sync_to_async(get_thumbnailer)(contact.profile_image)
            await sync_to_async(thumbnailer.delete_thumbnails)()
        except Exception as e:
            logger.warning(f"Could not delete thumbnails: {e}")
        await sync_to_async(contact.profile_image.delete)(save=False)
        contact.profile_image = None
        await contact.asave()

    await clear_cache("v2:entries", request)
    return {"avatar": None}
