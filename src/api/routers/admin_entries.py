import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.auth import JWT
from api.neo4j_auth import get_neo4j_role
from api.serializers.admin_entries import get_admin_entries
from api.types.admin_entry import AdminEntry
from api.utils import get_directory, get_site_from_request

logger = logging.getLogger(__name__)

router = APIRouter()

# The only roles that may read anything in this module.
#
# Hard-coded, unlike every other endpoint here, which resolves permissions
# through the AccessControl table. That table is data: a row granting `staff`
# read access to this endpoint is one careless edit, one bad fixture or one
# over-eager migration away, and nothing about that change would fail a test or
# meet a reviewer. This payload names who created and who owns every entry in
# the directory, so the list of roles allowed to read it belongs in code.
#
# tests/api/test_admin_entries_authorization.py pins this, including the case
# where an AccessControl row tries to grant staff full permissions.
ADMIN_ROLES = frozenset({"administrator", "superuser"})


async def require_admin_role(
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
) -> str:
    """Let administrators and superusers through; refuse everyone else.

    Deliberately not authorize_api: that consults AccessControl, and it also
    falls back to Django's `is_superuser` when the graph yields no role. Both
    are wrong here — the first for the reason above, the second because a
    Django superuser with no administrator access in this site's graph is not
    an administrator of this directory. The fallback is legacy; new endpoints
    do not inherit it.

    A suspended access yields no role from get_neo4j_role, so a suspended
    administrator is refused by the membership test without a special case.
    """
    site = await get_site_from_request(request)
    role = await get_neo4j_role(jwt, site) if jwt else None
    if role not in ADMIN_ROLES:
        logger.warning(
            "refused %s on %s for role=%r",
            request.method,
            request.url.path,
            role,
        )
        # No detail: an unauthorised caller does not need this endpoint's
        # existence or its requirements confirmed.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return role


@router.get("/admin/entries")
async def admin_entries(
    request: Request,
    role: Annotated[str, Depends(require_admin_role)],
) -> list[AdminEntry]:
    """The administrative fields for every entry, keyed by uid.

    Only what /api/v2/entries does not carry: the creation date, the contact
    timestamp, why an entry was deactivated, and the names behind the creator
    and owner uids. The page merges them onto the entries it already holds.

    Uncached, while /entries is cached per role. Not because a cache would go
    stale — every write invalidates it — but because caching buys nothing here:
    two administrators and three superusers read this, against the effectively
    unbounded anonymous traffic the /entries cache exists to absorb. That cache
    covers administrators too, deliberately, since it is what keeps the rest of
    the site fast for them.
    """
    directory = await get_directory(request)
    return await get_admin_entries(directory.name)
