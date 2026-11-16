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
from urllib.parse import quote, urljoin, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.auth import JWT, check_cookie_jwt
from api.neo4j_auth import get_neo4j_role
from api.serializers.clone import detect, execute
from api.serializers.clone import token as clone_token
from api.types.clone import (
    Blocker, EntryPreflight, ExecuteRequest, ExecuteResponse,
    ExportTokenRequest, ExportTokenResponse, PeerInstanceOut, PreflightRequest,
)
from asgiref.sync import sync_to_async

from api.utils import clear_cache, get_directory, get_site_from_request
from directory.models.core import sync_clear_effector_type_labels_cache
from directory.models import Directory, PeerInstance
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
                       jwt: Annotated[dict, Depends(JWT)],
                       _: Annotated[str, Depends(require_superuser)]) -> ExportTokenResponse:
    """Mint a token letting `target_origin` read this directory as this user.

    Called on the SOURCE, with the source's own session. The target it names is
    checked against this instance's peer registry: `inbound` is how a deployment
    refuses to be read, and an arbitrary origin in the request body must not be
    able to bypass it.
    """
    # The peer check first, before any lookup that can fail for its own
    # reasons. Resolving the directory ahead of it meant a misconfigured site
    # answered a *refused* request with an unrelated error, which reads as a
    # server fault rather than "that origin may not read this instance".
    allowed = [p async for p in PeerInstance.objects.filter(active=True, inbound=True).all()]
    if not any(body.target_origin.rstrip("/") == p.origin.rstrip("/") for p in allowed):
        # Names the fix, not just the refusal. Each deployment has its own
        # registry, and this one is the *source*: it checks its own `inbound`
        # row for the caller. Seeding only the target leaves this end with no
        # row at all, which is the likeliest reason to be here.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"{body.target_origin} is not registered here as a peer that may "
                f"read this instance. Add it with inbound=true on THIS deployment "
                f"(manage.py seed_peer_instances --write), not only on the target."
            ),
        )

    site = await get_site_from_request(request)
    directory = await _directory(request, body.directory)

    org_entry = await _org_entry_uid(site)
    token, ttl = clone_token.mint(
        sub=jwt.get("providerAccountId"),
        source_host=request.url.hostname,
        target_origin=body.target_origin.rstrip("/"),
        directory=directory.name,
        org_entry=org_entry,
        entry_uids=body.entry_uids,
    )
    return ExportTokenResponse(
        token=token, expires_in=ttl, directory=directory.name,
        source_origin=f"https://{request.url.hostname}",
        org_entry=org_entry,
    )


@router.delete("/clone/export-token")
async def burn_token(request: Request) -> dict:
    """Invalidate a token before it expires, when a batch ends."""
    raw = clone_token.bearer(request)
    if raw:
        clone_token.burn(raw, request_host=request.url.hostname)
    return {"burnt": bool(raw)}


async def directory_of_site(site, name: str) -> Directory:
    """The named directory, when it is one of this site's; 404 otherwise, whoever owns it."""
    directory = await Directory.objects.select_related("site").filter(site=site, name=name).afirst()
    if directory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no directory {name!r} on this site")
    return directory


async def _directory(request: Request, name: str | None) -> Directory:
    """The directory a clone reads or writes: the one named, or the site's own."""
    if name:
        return await directory_of_site(await get_site_from_request(request), name)
    return await get_directory(request)


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


def avatar_url(origin: str, path: str | None) -> str | None:
    """Where to download a picture the source names: on the source's origin, or nowhere."""
    if not path:
        return None
    url = urljoin(origin.rstrip("/") + "/", path)
    return url if urlparse(url).netloc == urlparse(origin).netloc else None


async def _schedules(peer: PeerInstance, uid: str, token: str) -> list[dict]:
    r = await _fetch(peer, f"/api/v2/entries/{uid}/schedules", token)
    return r.json() if r.status_code == 200 else []


async def _avatar(peer: PeerInstance, full: dict) -> tuple[str, bytes] | None:
    url = avatar_url(peer.origin, (full.get("avatar") or {}).get("raw"))
    if not url:
        return None
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=False) as client:
        r = await client.get(url)
    if r.status_code != 200 or not r.content:
        return None
    return url.rsplit("/", 1)[-1] or "avatar", r.content


@router.get("/clone/source/entries")
async def source_entries(request: Request, jwt: Annotated[dict | None, Depends(check_cookie_jwt)],
                         directory: str | None = None) -> list:
    """On the SOURCE: every entry the directory node holds, for a clone to pick from.

    Not the public list, which hides a porteur (it manages nothing): cloning a directory
    takes all of it. A superuser's, through the clone token or a session; a token reads
    only the directory it was minted for.
    """
    from api.serializers.allentries import createEntryResources
    from directory.utils import get_entries

    site = await get_site_from_request(request)
    if (await get_neo4j_role(jwt, site) if jwt else None) not in CLONE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    chosen = await _directory(request, directory)
    claims = getattr(request.state, "clone_claims", None)
    if claims is not None and claims.directory != chosen.name:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="this token reads another directory")
    return await createEntryResources(await get_entries(chosen, active=None, listed_only=False), request)


@router.get("/clone/relay/entries")
async def relay_entries(instance: str, token: str, request: Request,
                        _: Annotated[str, Depends(require_superuser)],
                        directory: str | None = None) -> dict:
    """The source's entries, fetched server-side, marked with what is already here.

    Relayed rather than fetched by the browser so the token never leaves this
    origin: a cross-origin request from the page would put a bearer credential
    into a context this instance does not control.

    `already_here` maps a source uid to the slug of the local entry that matches
    it, so the picker can grey out what cloning would only reject later. It is a
    courtesy rather than the gate — preflight is still the authority — and it is
    computed here because only this instance can answer it.

    `origin` travels so the page can resolve the avatar paths, which are
    relative to the *source*.
    """
    peer = await _peer(instance)
    r = await _fetch(peer, "/api/v2/clone/source/entries" + (f"?directory={quote(directory)}" if directory else ""), token)
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code,
                            detail=f"{peer.display_name} refused the entry list")
    entries = r.json()
    return {
        "entries": entries,
        "already_here": await detect.already_here(entries),
        "origin": peer.origin.rstrip("/"),
    }


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

    async def read_full(uid: str) -> dict | None:
        r = await _fetch(peer, f"/api/v2/fullentries/{uid}", body.token)
        return r.json() if r.status_code == 200 else None

    out: list[EntryPreflight] = []
    fulls: list[dict] = []
    for uid in body.entry_uids:
        full = await read_full(uid)
        if full is None:
            out.append(EntryPreflight(
                source_uid=uid, name="", effector={}, facility={},
                blockers=[Blocker(reason="unreadable", detail="the source refused this entry")],
            ))
        else:
            fulls.append(full)
    # A porteur of another directory is in no list: it comes along, so its services are
    # run by it here too.
    fulls += await execute.porteurs_to_add(fulls, read_full, batch=set(body.entry_uids))
    batch = {full.get("uid") for full in fulls}

    for full in fulls:
        uid = full.get("uid")
        eff, warnings = await detect.plan_effector(full)
        warnings = warnings + await execute.missing_here(full, batch=batch)
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
        elif await detect.slug_taken_here(full.get("slug")):
            blockers.append(Blocker(
                reason="slug_taken",
                detail=f"slug '{full.get('slug')}' is already used here by another entry",
                local_slug=full.get("slug"),
            ))

        out.append(EntryPreflight(
            source_uid=uid, name=full.get("name") or "",
            effector=eff, facility=fac, blockers=blockers, warnings=warnings,
            auto_clonable=eff.auto and fac.auto and not blockers,
        ))
    return out


@router.post("/clone/execute")
async def execute_clone(body: ExecuteRequest, request: Request,
                        jwt: Annotated[dict, Depends(JWT)],
                        _: Annotated[str, Depends(require_superuser)]) -> ExecuteResponse:
    """Clone the entries, one at a time; one failure never aborts the batch."""
    peer = await _peer(body.instance)
    site = await get_site_from_request(request)
    directory = await _directory(request, body.directory)
    org_uid = await _org_entry_uid(site)
    # The source's organization entry, taken from the request rather than the
    # token.
    #
    # The token is signed with the source's own derived key and is opaque here
    # by design — that is what lets two deployments trust each other without
    # sharing a secret. Reading it locally always failed, so `source_org_entry`
    # was always None, the MEMBER_OF remap never fired, and every cloned entry
    # arrived belonging to no organization: visible in /api/v2/entries and on
    # its own page, absent from every listing that filters on membership.
    source_org_entry = body.source_org_entry

    creator_uid = None
    from api.neo4j_auth import get_neo4j_user
    user = await get_neo4j_user(jwt)
    if user:
        creator_uid = str(user.uid)

    # Everything read first: the batch clones porteurs before their services, whatever
    # the order the superuser picked them in.
    refused, items, avatars = [], [], {}
    for res in body.resolutions:
        r = await _fetch(peer, f"/api/v2/fullentries/{res.source_uid}", body.token)
        if r.status_code != 200:
            refused.append(execute.CloneResult(
                source_uid=res.source_uid, status="failed",
                error=f"the source refused this entry ({r.status_code})"))
            continue
        full = r.json()
        full["schedules"] = await _schedules(peer, res.source_uid, body.token)
        picture = await _avatar(peer, full)
        if picture:
            avatars[full.get("uid")] = picture
        items.append((full, res))

    organization = await Organization.objects.filter(site=site).afirst()
    results = refused + await execute.clone_batch(
        items, avatars=avatars,
        directory_name=directory.name, org_uid=org_uid,
        source_org_entry=source_org_entry,
        creator_uid=creator_uid, organization=organization,
    )

    if any(x.status == "created" for x in results):
        # Once per batch: each call walks every Role x Directory key.
        await clear_cache("v2:entries", request)
        await clear_cache("v1:facilities", request)
        await clear_cache("v2:public/facilities", request)
        # The occupation labels, which a clone can add to.
        #
        # A cloned entry may bring an EffectorType this directory has never
        # listed — the point of cloning is usually that the person is new here.
        # The staff listing on the home page does not read the type from the
        # entry: cardCatEntries groups entries by type and then asks
        # genderedLabel for its name, which comes from this payload. Stale, the
        # new profession has no label and the group is simply absent from the
        # page, while the entry itself is present everywhere else — which is a
        # confusing way to find out a cache was missed.
        await sync_to_async(sync_clear_effector_type_labels_cache)()
    return ExecuteResponse(results=results)
