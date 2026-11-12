from typing import Annotated

from django.conf import settings
from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.auth import check_cookie_jwt
from api.neo4j_auth import get_neo4j_role, normalize_neo4j_role
from api.serializers.allentries import may_list, resolve_directory
from api.types.concern import Concern
from directory.concerns import concerns_of_directory

router = APIRouter()


@router.get("/concerns", response_model=list[Concern])
async def list_concerns(
    request: Request,
    jwt: Annotated[dict | None, Depends(check_cookie_jwt)],
    directory: str | None = None,
):
    """The conditions and situations a directory offers, each with the entries it selects.
    The directory is the site's own unless `directory` names a sibling; it is listed under the
    same rule as its entries."""
    chosen, minimum_role = await resolve_directory(request, directory)
    role = normalize_neo4j_role(await get_neo4j_role(jwt, chosen.site) or "anonymous")
    if not may_list(role, minimum_role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This directory is reserved")
    return await concerns_of_directory(chosen.name, settings.LANGUAGE_CODE)
