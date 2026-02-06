import logging
from typing import Annotated
from fastapi import APIRouter, Request, Depends, status, HTTPException
from neomodel import adb
from api.types.invitee import Invitee, InviteePost, InviteePatch
from access.asyncneomodels import Invitee as AsyncInvitee
from access.asyncneomodels import User as AsyncUser
from access.asyncneomodels import Account as AsyncAccount
from directory.models.agraph import Entry
from api.auth import authorize_api
from api.auth import JWT
from api.utils import get_site_from_request
from facility.models import Organization

logger = logging.getLogger(__name__)

router = APIRouter()


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
    query = """
    MATCH (entry:Entry {uid: $entry_uid})<-[:INVITED_TO]-(invitee:Invitee)
    RETURN invitee
    """
    results, _ = await adb.cypher_query(query, {"entry_uid": str(organization.neomodel_uid)}, resolve_objects=True)

    invitee_list = []
    if results:
        for row in results:
            invitee_node = row[0]
            invitee_list.append(Invitee.model_validate(invitee_node.__properties__))

    return invitee_list


@router.post("/invitee", status_code=status.HTTP_201_CREATED)
async def create_invitee(
    item: InviteePost,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)]
) -> Invitee:
    await authorize_api("invitees_v2", request, jwt)

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
    try:
        account = await AsyncAccount.nodes.get(uid=jwt["providerAccountId"])
    except AsyncAccount.DoesNotExist as e:
        logger.error(f'Failed to get Account with sub {jwt["providerAccountId"]}: {e}')
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Account with sub {jwt["providerAccountId"]} not found'
        )
    try:
        user = (await account.user.all())[0]
        await new_invitee.createdBy.connect(user)
    except Exception as e:
        logger.error(f"Failed to connect to User: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User linked to Account {account} not found"
        )
    return Invitee.model_validate(new_invitee.__properties__)


@router.patch("/invitee/{invitee_uid}")
async def update_invitee(
    invitee_uid: str,
    item: InviteePatch,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)]
) -> Invitee:
    await authorize_api("invitees_v2", request, jwt)

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
