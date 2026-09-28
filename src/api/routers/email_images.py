"""The images an organization links from its HTML emails.

A thin shell over mailer.gallery: authorise, resolve the site's organization,
and map the gallery's exceptions to status codes whose bodies carry a code the
frontend translates. Gated by api.email_access, like the templates the images
go in: administrators and higher see them, the organization's chosen role
changes them.
"""

import logging
from typing import Annotated
from uuid import UUID

from asgiref.sync import sync_to_async
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status

from api.auth import JWT
from api.email_access import email_access
from api.types.email_template import EmailImageOut, EmailImagePatch
from mailer.gallery import (
    ImageInvalid,
    NameTaken,
    add_image,
    delete_image,
    image_urls,
    list_images,
    update_image,
)
from mailer.models import EmailImage
from mailer.templating import organization_site_url

logger = logging.getLogger(__name__)

router = APIRouter()

async def _organization(request: Request, jwt: dict, *, edit: bool = False):
    """(organization, the site's public URL), or 403/404."""
    access = await email_access(request, jwt, edit=edit)
    return access.organization, organization_site_url(access.organization, access.site.domain)


def _out(image, site_url: str) -> EmailImageOut:
    return EmailImageOut(
        uid=image.uid,
        name=image.name,
        alt=image.alt,
        width=image.width,
        height=image.height,
        size=image.size,
        created=image.created,
        **image_urls(image, site_url),
    )


def _not_found():
    return HTTPException(status.HTTP_404_NOT_FOUND, detail="Image not found")


@router.get("/email-images", response_model=list[EmailImageOut])
async def get_email_images(request: Request, jwt: Annotated[dict, Depends(JWT)]):
    organization, site_url = await _organization(request, jwt)

    def build():
        return [_out(image, site_url) for image in list_images(organization)]

    return await sync_to_async(build)()


@router.post("/email-images", response_model=EmailImageOut, status_code=status.HTTP_201_CREATED)
async def post_email_image(
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
    file: UploadFile = File(...),
    name: str = Form(""),
    alt: str = Form(""),
):
    organization, site_url = await _organization(request, jwt, edit=True)
    content = await file.read()

    def build():
        return _out(add_image(organization, file.filename or "", content, name=name, alt=alt), site_url)

    try:
        return await sync_to_async(build)()
    except ImageInvalid as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": error.code})


@router.patch("/email-images/{uid}", response_model=EmailImageOut)
async def patch_email_image(
    uid: UUID,
    payload: EmailImagePatch,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    organization, site_url = await _organization(request, jwt, edit=True)

    def build():
        return _out(update_image(organization, uid, name=payload.name, alt=payload.alt), site_url)

    try:
        return await sync_to_async(build)()
    except EmailImage.DoesNotExist:
        raise _not_found()
    except NameTaken:
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"code": "name_taken"})
    except ImageInvalid as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": error.code})


@router.delete("/email-images/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_email_image(uid: UUID, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    organization, _ = await _organization(request, jwt, edit=True)
    try:
        await sync_to_async(delete_image)(organization, uid)
    except EmailImage.DoesNotExist:
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
