"""Clone an entry from another deployment of this app.

dev, staging and production have their own Postgres and Neo4j, so this crosses a
network boundary: the target fetches from the source over HTTPS using a token
the source minted for the superuser after they signed in there.

Only two things here are new. The **token** exists because a session cookie is
encrypted with its own instance's AUTH_SECRET and cannot be read elsewhere. The
**collision detection** exists because nothing in the app answers "does this
already exist here" before writing — assert_slug_is_free raises during the
write, too late to preview.

Everything else reuses what is already there: reads come from /entries and
/fullentries (widened in api.auth.check_cookie_jwt to accept a clone token), and
the writes follow create_facility's and create_entry's own rules.
"""
import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.auth import JWT
from api.neo4j_auth import get_neo4j_role
from api.serializers.clone import detect, execute
from api.serializers.clone import token as clone_token
from api.types.clone import (
    Blocker, EntryPreflight, ExecuteRequest, ExecuteResponse,
    ExportTokenRequest, ExportTokenResponse, PeerInstanceOut, PreflightRequest,
)
from api.utils import clear_cache, get_directory, get_site_from_request
from directory.models import PeerInstance
from facility.models import Organization

logger = logging.getLogger(__name__)

router = APIRouter()

#: Cloning reads a whole directory's contact data and writes entries. Superuser
#: only, hard-coded for the reason admin_entries.py documents: a role list in
#: the AccessControl table is one careless row away from being wider.
CLONE_ROLES = frozenset({"superuser"})

HTTP_TIMEOUT = 20.0


async def require_superuser(request: Request, jwt: Annotated[dict, Depends(JWT)]) -> str:
    site = await get_site_from_request(request)
    role = await get_neo4j_role(jwt, site) if jwt else None
    if role not in CLONE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return role


async def _org_entry_uid(site) -> str | None:
    try:
        org = await Organization.objects.aget(site=site)
    except Organization.DoesNotExist:
        return None
    return org.neomodel_uid.hex if org.neomodel_uid else None


@router.get("/clone/instances")
async def instances(request: Request,
                    _: Annotated[str, Depends(require_superuser)]) -> list[PeerInstanceOut]:
    """The peers this instance may pull from."""
    here = request.url.hostname
    # A list comprehension over the async iterator: `async for` on a queryset
    # still evaluates it lazily in a sync context on first touch, which raises
    # SynchronousOnlyOperation under the ASGI loop.
    peers = [p async for p in PeerInstance.objects.filter(active=True, outbound=True).all()]
    return [
        PeerInstanceOut(name=p.name, display_name=p.display_name, origin=p.origin)
        for p in peers
        # Never offer this instance to itself.
        if not (p.origin and here and here in p.origin)
    ]


@router.post("/clone/export-token")
async def export_token(body: ExportTokenRequest, request: Request,
                       _: Annotated[str, Depends(require_superuser)]) -> ExportTokenResponse:
    """Mint a token letting `target_origin` read this directory as this user.

    Called on the SOURCE, with the source's own session. The target it names is
    checked against this instance's peer registry: `inbound` is how a deployment
    refuses to be read, and an arbitrary origin in the request body must not be
    able to bypass it.
    """
    jwt = JWT(request)
    site = await get_site_from_request(request)
    directory = await get_directory(request)

    allowed = [p async for p in PeerInstance.objects.filter(active=True, inbound=True).all()]
    if not any(body.target_origin.rstrip("/") == p.origin.rstrip("/") for p in allowed):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{body.target_origin} is not a peer allowed to read this instance",
        )
    if body.entry_uids and len(body.entry_uids) > clone_token.MAX_ENTRIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"at most {clone_token.MAX_ENTRIES} entries per token",
        )

    token, ttl = clone_token.mint(
        sub=jwt.get("providerAccountId"),
        source_host=request.url.hostname,
        target_origin=body.target_origin.rstrip("/"),
        directory=directory.name,
        org_entry=await _org_entry_uid(site),
        entry_uids=body.entry_uids,
    )
    return ExportTokenResponse(
        token=token, expires_in=ttl, directory=directory.name,
        source_origin=f"https://{request.url.hostname}",
    )


@router.delete("/clone/export-token")
async def burn_token(request: Request) -> dict:
    """Invalidate a token before it expires, when a batch ends."""
    raw = clone_token.bearer(request)
    if raw:
        clone_token.burn(raw, request_host=request.url.hostname)
    return {"burnt": bool(raw)}


async def _peer(name: str) -> PeerInstance:
    try:
        return await PeerInstance.objects.aget(name=name, active=True, outbound=True)
    except PeerInstance.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"no active peer named {name!r}")


async def _fetch(peer: PeerInstance, path: str, token: str) -> httpx.Response:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=False) as client:
        return await client.get(
            f"{peer.origin.rstrip('/')}{path}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )


@router.get("/clone/relay/entries")
async def relay_entries(instance: str, token: str, request: Request,
                        _: Annotated[str, Depends(require_superuser)]) -> list[dict]:
    """The source's entries, fetched server-side.

    Relayed rather than fetched by the browser so the token never leaves this
    origin: a cross-origin request from the page would put a bearer credential
    into a context this instance does not control.
    """
    peer = await _peer(instance)
    r = await _fetch(peer, "/api/v2/entries", token)
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code,
                            detail=f"{peer.display_name} refused the entry list")
    return r.json()


@router.post("/clone/preflight")
async def preflight(body: PreflightRequest, request: Request,
                    _: Annotated[str, Depends(require_superuser)]) -> list[EntryPreflight]:
    """What cloning these entries would do, before doing any of it."""
    peer = await _peer(body.instance)
    site = await get_site_from_request(request)
    org_uid = await _org_entry_uid(site)
    if not org_uid:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="this site has no organization entry to attach facilities to")

    out: list[EntryPreflight] = []
    for uid in body.entry_uids[: clone_token.MAX_ENTRIES]:
        r = await _fetch(peer, f"/api/v2/fullentries/{uid}", body.token)
        if r.status_code != 200:
            out.append(EntryPreflight(
                source_uid=uid, name="", effector={}, facility={},
                blockers=[Blocker(reason="unreadable",
                                  detail=f"the source refused this entry ({r.status_code})")],
            ))
            continue
        full = r.json()
        eff, warnings = await detect.plan_effector(full)
        fac = await detect.plan_facility(full, org_uid)

        blockers: list[Blocker] = []
        if not await detect.resolve_effector_type(full.get("effector_type") or {}):
            blockers.append(Blocker(
                reason="effector_type",
                detail=f"'{(full.get('effector_type') or {}).get('label')}' does not exist here",
            ))
        if fac.default_resolution == "create" and not await detect.resolve_commune(
            full.get("address") or {}
        ):
            blockers.append(Blocker(
                reason="commune",
                detail=f"commune '{(full.get('address') or {}).get('city')}' does not exist here",
            ))
        existing = await detect.entry_already_here(
            eff.local_uid,
            await detect.resolve_effector_type(full.get("effector_type") or {}),
            fac.local_uid,
        )
        if existing:
            blockers.append(Blocker(
                reason="entry_exists",
                detail="this person, occupation and place already exist here",
                local_slug=existing,
            ))

        out.append(EntryPreflight(
            source_uid=uid, name=full.get("name") or "",
            effector=eff, facility=fac, blockers=blockers, warnings=warnings,
            auto_clonable=eff.auto and fac.auto and not blockers,
        ))
    return out


@router.post("/clone/execute")
async def execute_clone(body: ExecuteRequest, request: Request,
                        _: Annotated[str, Depends(require_superuser)]) -> ExecuteResponse:
    """Clone the entries, one at a time; one failure never aborts the batch."""
    peer = await _peer(body.instance)
    site = await get_site_from_request(request)
    directory = await get_directory(request)
    org_uid = await _org_entry_uid(site)
    claims = None
    try:
        claims = clone_token.read(body.token, request_host=peer.origin.split("//")[-1])
    except HTTPException:
        # The token is the source's to verify; the target only relays it. A
        # local read failure is not a reason to refuse.
        pass

    jwt = JWT(request)
    creator_uid = None
    from api.neo4j_auth import get_neo4j_user
    user = await get_neo4j_user(jwt)
    if user:
        creator_uid = str(user.uid)

    results = []
    for res in body.resolutions[: clone_token.MAX_ENTRIES]:
        r = await _fetch(peer, f"/api/v2/fullentries/{res.source_uid}", body.token)
        if r.status_code != 200:
            results.append(execute.CloneResult(
                source_uid=res.source_uid, status="failed",
                error=f"the source refused this entry ({r.status_code})"))
            continue
        results.append(await execute.clone_one(
            r.json(), res,
            directory_name=directory.name, org_uid=org_uid,
            source_org_entry=claims.org_entry if claims else None,
            creator_uid=creator_uid,
        ))

    if any(x.status == "created" for x in results):
        # Once per batch: each call walks every Role x Directory key.
        await clear_cache("v2:entries", request)
        await clear_cache("v1:facilities", request)
        await clear_cache("v2:public/facilities", request)
    return ExecuteResponse(results=results)
