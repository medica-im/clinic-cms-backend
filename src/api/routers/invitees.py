import logging
from typing import Annotated
from fastapi import APIRouter, Request, Depends, status, HTTPException
from fastapi.responses import StreamingResponse
from neomodel import adb
from asgiref.sync import sync_to_async
from api.types.invitee import AddressIssue, EmailDelivery, Invitee, InviteePost, InviteePatch, ResendRequest
from access.asyncneomodels import Invitee as AsyncInvitee
from access.asyncneomodels import User as AsyncUser
from access.asyncneomodels import Account as AsyncAccount
from directory.models.agraph import Entry
from api.auth import JWT, get_neo4j_role, authorize_api
from access.active_access import is_member
from api.utils import get_site_from_request
from facility.models import Organization
from api.serializers.invitee import notification_email
from mailer.delivery import latest_deliveries, resend_refusal
from mailer.suppression import blocking, is_opted_out, issue_payload, issues_for, normalize

logger = logging.getLogger(__name__)

router = APIRouter()


async def with_email_delivery(invitees: list[Invitee], organization=None) -> list[Invitee]:
    """Attach each invitation's latest email attempt, and why its address is
    not sent to automatically if it is (mailer.suppression) -- the global
    records, plus this organization's own refusals."""
    rows = await sync_to_async(latest_deliveries)([invitee.uid for invitee in invitees])
    scope = organization if isinstance(organization, Organization) else None
    issues = await sync_to_async(issues_for)([invitee.email for invitee in invitees], scope)
    for invitee in invitees:
        row = rows.get(invitee.uid)
        if row is not None:
            invitee.emailDelivery = EmailDelivery.from_row(row)
        issue = issue_payload(issues.get(normalize(invitee.email or "")))
        if issue is not None:
            invitee.addressIssue = AddressIssue(**issue)
    return invitees


async def site_organization(request: Request) -> Organization | None:
    site = await get_site_from_request(request)
    return await Organization.objects.filter(site=site).afirst()


async def verify_invitee_ownership(request: Request, invitee_uid: str):
    """Verify that an invitee belongs to the requesting site's organization."""
    site = await get_site_from_request(request)
    try:
        organization = await Organization.objects.aget(site=site)
    except Organization.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found for this site"
        )
    if not organization.neomodel_uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization does not have a neomodel_uid"
        )
    query = """
    MATCH (entry:Entry {uid: $entry_uid})<-[:INVITED_TO]-(invitee:Invitee {uid: $invitee_uid})
    RETURN invitee
    """
    results, _ = await adb.cypher_query(
        query,
        {"entry_uid": organization.neomodel_uid.hex, "invitee_uid": invitee_uid}
    )
    if not results:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invitee does not belong to this organization"
        )


@router.get("/invitees")
async def invitees(request: Request, jwt: Annotated[dict, Depends(JWT)]) -> list[Invitee]:
    await authorize_api("invitees_v2", request, jwt)

    # Get Site and Organization
    site = await get_site_from_request(request)
    try:
        organization = await Organization.objects.aget(site=site)
    except Organization.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found for this site"
        )

    if not organization.neomodel_uid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization does not have a neomodel_uid"
        )

    # Query Invitees connected to the Entry node with uid matching neomodel_uid
    entry_uid = str(organization.neomodel_uid.hex)
    logger.info(f"Searching for Invitees connected to Entry with uid: {entry_uid}")

    query = """
    MATCH (entry:Entry {uid: $entry_uid})<-[:INVITED_TO]-(invitee:Invitee)
    OPTIONAL MATCH (invitee)-[:CREATED_BY]->(user:User)
    RETURN invitee, user.uid AS createdBy
    """
    results, _ = await adb.cypher_query(query, {"entry_uid": entry_uid}, resolve_objects=False)

    logger.info(f"Query returned {len(results)} results")

    invitee_list = []
    if results:
        for row in results:
            props = dict(row[0])
            props["createdBy"] = row[1]
            invitee_list.append(Invitee.model_validate(props))

    return await with_email_delivery(invitee_list, organization)


# Before /invitees/{invitee_uid}, or "events" would be read as a uid.
@router.get("/invitees/events")
async def invitee_events(request: Request, jwt: Annotated[dict, Depends(JWT)]):
    """Where each invitation's email stands, pushed as it changes (SSE).

    Guarded like the list it feeds; passes on only this organization's
    changes, and ends when the client leaves or the server stops
    (mailer.live.stream_changes).
    """
    await authorize_api("invitees_v2", request, jwt)
    site = await get_site_from_request(request)
    organization = await Organization.objects.filter(site=site).afirst()
    if organization is None or not organization.neomodel_uid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found for this site")
    entry_uid = organization.neomodel_uid.hex

    async def stream():
        import redis.asyncio as aioredis
        from django.conf import settings
        from api import stopping
        from mailer.live import CHANNEL, stream_changes

        client = aioredis.Redis(host=settings.REDIS_HOST, port=int(settings.REDIS_PORT))
        pubsub = client.pubsub()
        await pubsub.subscribe(CHANNEL)
        try:
            async for frame in stream_changes(pubsub, entry_uid, request.is_disconnected, stopping.event()):
                yield frame
        finally:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()
            await client.aclose()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        # X-Accel-Buffering: nginx would otherwise hold the events back.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )



@router.get("/invitees/{invitee_uid}")
async def get_invitee(
    invitee_uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)]
) -> Invitee:
    await authorize_api("invitees_v2", request, jwt)

    query = """
    MATCH (invitee:Invitee {uid: $invitee_uid})
    OPTIONAL MATCH (invitee)-[:CREATED_BY]->(user:User)
    RETURN invitee, user.uid AS createdBy
    """
    results, _ = await adb.cypher_query(query, {"invitee_uid": invitee_uid}, resolve_objects=False)
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invitee with uid {invitee_uid} not found"
        )
    props = dict(results[0][0])
    props["createdBy"] = results[0][1]
    return (await with_email_delivery([Invitee.model_validate(props)], await site_organization(request)))[0]


@router.post("/invitees", status_code=status.HTTP_201_CREATED)
async def create_invitee(
    item: InviteePost,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)]
) -> Invitee:
    await authorize_api("invitees_v2", request, jwt)
    site = await get_site_from_request(request)

    # Verify the entry belongs to this site's organization
    try:
        organization = await Organization.objects.aget(site=site)
    except Organization.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found for this site"
        )
    if not organization.neomodel_uid or item.entry != organization.neomodel_uid.hex:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Entry does not belong to this organization"
        )

    # Check for existing invitation with same email and entry
    duplicate_query = """
    MATCH (entry:Entry {uid: $entry_uid})<-[:INVITED_TO]-(invitee:Invitee {email: $email})
    RETURN invitee
    """
    results, _ = await adb.cypher_query(
        duplicate_query,
        {"entry_uid": item.entry, "email": item.email}
    )
    if results:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
        "code": "DUPLICATE_EMAIL",
        "message": f"Une invitation adressée à {item.email} existe déjà."
    }
        )
    if await is_member(item.email, item.entry):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "ALREADY_MEMBER",
                "message": f"{item.email} a déjà accès à ce site.",
            },
        )

    role = await get_neo4j_role(jwt, site)
    logger.debug(f"{role=} {item.role=}")
    if item.role == "superuser" and role != "superuser":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can create superuser invitees"
        )

    # Create the Invitee node
    new_invitee = await AsyncInvitee(
        email=item.email,
        role=item.role,
        name=item.name
    ).save()

    try:
        entry = await Entry.nodes.get(uid=item.entry)
        await new_invitee.entry.connect(entry)
    except Exception as e:
        logger.error(f"Failed to connect to Entry {item.entry}: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entry with uid {item.entry} not found"
        )
    sub=jwt["providerAccountId"]
    logger.debug(f"JWT providerAccountId {sub=}")
    try:
        query = """
        MATCH (a:Account {sub: $sub})<-[:HAS_ACCOUNT]-(u:User)
        MATCH (i:Invitee {uid: $invitee_uid})
        MERGE (i)-[:CREATED_BY]->(u)
        RETURN u.uid AS userUid
        """
        results, _ = await adb.cypher_query(
            query,
            {"sub": sub, "invitee_uid": new_invitee.uid}
        )
        if not results:
            logger.error(f'No User found linked to Account with sub {sub}')
    except Exception as e:
        logger.error(f"Failed to connect createdBy for Invitee: {e}")
    invitee = Invitee.model_validate(new_invitee.__properties__)
    await notification_email(invitee, site)
    return (await with_email_delivery([invitee], await site_organization(request)))[0]


@router.post("/invitees/{invitee_uid}/resend")
async def resend_invitee_email(
    invitee_uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
    body: ResendRequest | None = None,
) -> Invitee:
    """Send the invitation's email again, with the organization's current
    template. A new EmailDelivery row is recorded, so an earlier failure stays
    in the history. 409 with a code when it may not be (resend_refusal), when
    the address is remembered as dead (address_rejected: send with force once
    checked) or the person refused this organization's mail
    (address_opted_out: never)."""
    await authorize_api("invitees_v2", request, jwt)
    await verify_invitee_ownership(request, invitee_uid)
    try:
        node = await AsyncInvitee.nodes.get(uid=invitee_uid)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invitee with uid {invitee_uid} not found"
        )
    invitee = Invitee.model_validate(node.__properties__)
    latest = (await sync_to_async(latest_deliveries)([invitee_uid])).get(invitee_uid)
    refusal = resend_refusal(invitee, latest)
    if refusal:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": refusal})
    organization = await site_organization(request)
    force = bool(body and body.force)
    blocked = await sync_to_async(blocking)(invitee.email or "", organization)
    if blocked is not None and (is_opted_out(blocked) or not force):
        code = "address_opted_out" if is_opted_out(blocked) else "address_rejected"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": code, **issue_payload(blocked)})
    site = await get_site_from_request(request)
    await notification_email(invitee, site, force=force)
    return (await with_email_delivery([invitee], organization))[0]


@router.patch("/invitees/{invitee_uid}")
async def update_invitee(
    invitee_uid: str,
    item: InviteePatch,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)]
) -> Invitee:
    await authorize_api("invitees_v2", request, jwt)
    await verify_invitee_ownership(request, invitee_uid)

    # Get the Invitee node
    try:
        invitee = await AsyncInvitee.nodes.get(uid=invitee_uid)
    except Exception as e:
        logger.error(f"Failed to get Invitee {invitee_uid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invitee with uid {invitee_uid} not found"
        )

    # Update only the fields that were provided
    address_changed = item.email is not None and normalize(item.email) != normalize(invitee.email or "")
    if item.email is not None:
        invitee.email = item.email
    if item.role is not None:
        invitee.role = item.role
    if item.name is not None:
        invitee.name = item.name
    if item.active is not None:
        invitee.active = item.active

    # Save the updated invitee
    updated_invitee = await invitee.save()
    updated = Invitee.model_validate(updated_invitee.__properties__)

    # A corrected address: the invitation goes to it straight away, unless
    # it can no longer be used. The old address may have bounced; this one
    # is a new attempt, judged on its own.
    usable = not updated.redeemedAt and updated.active is not False
    if address_changed and usable:
        await notification_email(updated, await get_site_from_request(request))

    return (await with_email_delivery([updated], await site_organization(request)))[0]


@router.delete("/invitees/{invitee_uid}")
async def delete_single_invitee(
    invitee_uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)]
):
    """
    Delete a single Invitee by uid.

    DELETE /invitees/{invitee_uid} - Deletes one Invitee with the specified uid
    """
    await authorize_api("invitees_v2", request, jwt)
    await verify_invitee_ownership(request, invitee_uid)

    # Get and delete the Invitee
    try:
        invitee = await AsyncInvitee.nodes.get(uid=invitee_uid)
        await invitee.delete()
    except Exception as e:
        logger.error(f"Failed to get or delete Invitee {invitee_uid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invitee with uid {invitee_uid} not found"
        )

    return {"message": "Invitee deleted successfully"}


@router.delete("/invitees")
async def delete_multiple_invitees(
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
    ids: str | None = None
):
    """
    Delete multiple Invitees or all Invitees for the organization.

    DELETE /invitees?ids=uid1,uid2,uid3 - Deletes specific Invitees (max 50)
    DELETE /invitees - Deletes all Invitees linked to the Site/Entry

    Maximum 50 UUIDs based on URL length constraints:
    - Conservative browser URL limit: ~2,000 characters
    - UUID4 length: 36 characters + 1 comma separator
    - Allows ~46 UUIDs safely, rounded to 50 for usability
    """
    await authorize_api("invitees_v2", request, jwt)

    # Get Site and Organization
    site = await get_site_from_request(request)
    try:
        organization = await Organization.objects.aget(site=site)
    except Organization.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found for this site"
        )

    if not organization.neomodel_uid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization does not have a neomodel_uid"
        )

    if ids:
        # Delete multiple specific Invitees
        uid_list = [uid.strip() for uid in ids.split(",")]

        if len(uid_list) > 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum of 50 ids allowed (URL length constraint)"
            )

        # Verify all Invitees belong to this organization's Entry
        verify_query = """
        MATCH (entry:Entry {uid: $entry_uid})<-[:INVITED_TO]-(invitee:Invitee)
        WHERE invitee.uid IN $uid_list
        RETURN invitee.uid as uid
        """
        results, _ = await adb.cypher_query(
            verify_query,
            {"entry_uid": str(organization.neomodel_uid), "uid_list": uid_list}
        )

        verified_uids = [row[0] for row in results] if results else []

        if len(verified_uids) != len(uid_list):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Some Invitees do not belong to this organization or do not exist"
            )

        # Delete the verified Invitees
        delete_query = """
        MATCH (invitee:Invitee)
        WHERE invitee.uid IN $uid_list
        DETACH DELETE invitee
        """
        await adb.cypher_query(delete_query, {"uid_list": verified_uids})

        return {
            "message": f"{len(verified_uids)} Invitee(s) deleted successfully",
            "deleted_count": len(verified_uids)
        }
    else:
        # Delete all Invitees for this organization's Entry
        delete_query = """
        MATCH (entry:Entry {uid: $entry_uid})<-[:INVITED_TO]-(invitee:Invitee)
        WITH invitee
        DETACH DELETE invitee
        RETURN count(invitee) as count
        """
        results, _ = await adb.cypher_query(
            delete_query,
            {"entry_uid": str(organization.neomodel_uid)}
        )

        deleted_count = results[0][0] if results else 0

        return {
            "message": f"All {deleted_count} Invitees for this organization deleted successfully"
        }
