"""Changing an entry's effector type from its page.

    GET  /entries/{uid}/effector-type/permission   may the caller, until when
    GET  /entries/{uid}/effector-type/preview      tags the change would remove
    PUT  /entries/{uid}/effector-type              the change

A thin shell over api.serializers.entry_type: the permission is answered per
user and never cached, like /facilities/{uid}/can-edit, so the pen on the
page and the write can never disagree; refusals are codes the page words.
"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from api.auth import JWT
from api.serializers.entry_type import (
    EntryTypeRefused,
    change_entry_type,
    preview_removed_tags,
    type_edit_context,
)
from api.utils import clear_cache

router = APIRouter()


class TypeEditPermissionOut(BaseModel):
    allowed: bool
    reason: Literal["not_allowed", "expired", "no_date"] | None
    window_days: int | None
    deadline: datetime | None
    created_at: int | None


class RemovedTag(BaseModel):
    uid: str
    label: str | None


class TypePreview(BaseModel):
    removed_tags: list[RemovedTag]


class TypeChange(BaseModel):
    effector_type: str


class TypeChanged(BaseModel):
    uid: str
    slug: str | None
    removed_tags: list[RemovedTag]


async def _context(uid: str, request: Request, jwt: dict, *, must_be_allowed: bool = False):
    context = await type_edit_context(uid, request, jwt)
    if context is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Entry not found")
    if must_be_allowed and not context.permission.allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": context.permission.reason})
    return context


@router.get("/entries/{uid}/effector-type/permission", response_model=TypeEditPermissionOut)
async def get_type_edit_permission(uid: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    context = await _context(uid, request, jwt)
    p = context.permission
    return TypeEditPermissionOut(
        allowed=p.allowed,
        reason=p.reason,
        window_days=p.window_days,
        deadline=p.deadline,
        created_at=context.created_at_ms,
    )


@router.get("/entries/{uid}/effector-type/preview", response_model=TypePreview)
async def preview_type_change(
    uid: str, effector_type: str, request: Request, jwt: Annotated[dict, Depends(JWT)]
):
    await _context(uid, request, jwt, must_be_allowed=True)
    return TypePreview(removed_tags=await preview_removed_tags(uid, effector_type))


@router.put("/entries/{uid}/effector-type", response_model=TypeChanged)
async def put_entry_type(
    uid: str, body: TypeChange, request: Request, jwt: Annotated[dict, Depends(JWT)]
):
    context = await _context(uid, request, jwt, must_be_allowed=True)
    try:
        result = await change_entry_type(context, body.effector_type)
    except EntryTypeRefused as refusal:
        code = status.HTTP_422_UNPROCESSABLE_ENTITY if refusal.code == "unknown_type" else status.HTTP_409_CONFLICT
        raise HTTPException(code, detail={"code": refusal.code, **refusal.detail})
    await clear_cache("v2:entries", request)
    return result
