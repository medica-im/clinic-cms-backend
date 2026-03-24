import logging
from typing import Annotated
from fastapi import APIRouter, Request, Depends, status, HTTPException
from neomodel import adb
from api.types.invitee import Invitee, InviteePost, InviteePatch
from access.asyncneomodels import Invitee as AsyncInvitee
from access.asyncneomodels import User as AsyncUser
from access.asyncneomodels import Account as AsyncAccount
from directory.models.agraph import Entry
from api.auth import JWT, get_neo4j_role, authorize_api, get_user, get_role
from api.utils import get_site_from_request
from facility.models import Organization
from access.models import Role
from api.serializers.invitee import notification_email

logger = logging.getLogger(__name__)

router = APIRouter()


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

    return invitee_list


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
    return Invitee.model_validate(props)


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

    role = await get_neo4j_role(jwt, site)
    logger.debug(f"neo4j {role=}")
    if not role:
        user = await get_user(jwt)
        logger.debug(f"{user=}")
        _role: Role = await get_role(user, site)
        role = _role.name
        logger.debug(f"django {role=}")
    logger.debug(f"{item.role=}")
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
    return invitee


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

    return Invitee.model_validate(updated_invitee.__properties__)


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
