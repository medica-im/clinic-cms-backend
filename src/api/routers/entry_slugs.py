"""Where an entry's former slug leads now (directory.EntrySlug).

The entry page asks when /fullentries/slug/{slug} answers 404, and redirects
to the current slug. Public, like the entry pages it serves.

Changing a slug from the entry page (directory/entry_slug.py):

    GET  /entries/{uid}/slug/permission   may the caller
    GET  /entries/{uid}/slug/check?slug=  is it free, and what else is
    PUT  /entries/{uid}/slug              the change; the old slug redirects
"""

from typing import Annotated, Literal

from asgiref.sync import sync_to_async
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from api.auth import JWT
from api.utils import clear_cache
from directory.entry_slug import EntrySlugRefused, change_entry_slug, check_entry_slug, slug_edit_context

from directory.models import EntrySlug
from directory.models.agraph import Entry as AgraphEntry

router = APIRouter()


class CurrentSlug(BaseModel):
    uid: str
    slug: str


def former_slug_entry(slug: str) -> str | None:
    row = EntrySlug.objects.filter(slug=slug).first()
    return row.entry_uid if row else None


@router.get("/entry-slugs/{slug}", response_model=CurrentSlug)
async def current_slug(slug: str) -> CurrentSlug:
    entry_uid = await sync_to_async(former_slug_entry)(slug)
    entry = await AgraphEntry.nodes.get_or_none(uid=entry_uid) if entry_uid else None
    if entry is None or not entry.slug:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No entry had this slug")
    return CurrentSlug(uid=entry.uid, slug=entry.slug)


class SlugEditPermission(BaseModel):
    allowed: bool


class SlugCheck(BaseModel):
    slug: str
    free: bool
    reason: Literal["invalid", "taken"] | None
    suggestions: list[str]


class SlugChange(BaseModel):
    slug: str


class SlugChanged(BaseModel):
    uid: str
    slug: str


async def _allowed(uid: str, request: Request, jwt: dict, *, must_be_allowed: bool = True):
    context = await slug_edit_context(uid, request, jwt)
    if context is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Entry not found")
    if must_be_allowed and not context.allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "not_allowed"})
    return context


@router.get("/entries/{uid}/slug/permission", response_model=SlugEditPermission)
async def get_slug_edit_permission(uid: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    """Whether the caller may change this entry's slug: answered per user, never cached."""
    context = await _allowed(uid, request, jwt, must_be_allowed=False)
    return SlugEditPermission(allowed=context.allowed)


@router.get("/entries/{uid}/slug/check", response_model=SlugCheck)
async def check_slug(uid: str, slug: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await _allowed(uid, request, jwt)
    return SlugCheck(**await check_entry_slug(uid, slug))


@router.put("/entries/{uid}/slug", response_model=SlugChanged)
async def put_slug(uid: str, body: SlugChange, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    context = await _allowed(uid, request, jwt)
    try:
        slug = await change_entry_slug(uid, body.slug, context.caller_uid)
    except EntrySlugRefused as refusal:
        code = status.HTTP_409_CONFLICT if refusal.code == "taken" else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(code, detail={"code": refusal.code})
    await clear_cache("v2:entries", request)
    return SlugChanged(uid=uid, slug=slug)
