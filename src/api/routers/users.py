import logging
from typing import Annotated

from fastapi import APIRouter, Request, Depends, status, HTTPException
from neomodel import adb

from api.types.user import User, AccountOut, AccessOut
from api.auth import JWT, authorize_api
from api.utils import get_site_from_request
from facility.models import Organization

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/users")
async def get_users(
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
) -> list[User]:
    await authorize_api("users_v2", request, jwt)

    site = await get_site_from_request(request)
    try:
        organization = await Organization.objects.aget(site=site)
    except Organization.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found for this site",
        )

    if not organization.neomodel_uid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization does not have a neomodel_uid",
        )

    entry_uid = str(organization.neomodel_uid.hex)

    query = """
    MATCH (u:User)-[:HAS_ACCESS]->(ac:Access {active: true})-[:ACCESS_TO]->(e:Entry {uid: $entry_uid})
    OPTIONAL MATCH (u)-[:HAS_ACCOUNT]->(a:Account)
    RETURN u, collect(DISTINCT a) AS accounts, collect(DISTINCT ac) AS accesses
    """
    results, _ = await adb.cypher_query(
        query, {"entry_uid": entry_uid}, resolve_objects=True
    )
    logger.debug(f"{results=}")
    user_list = []
    for row in results:
        logger.debug(f"{row=}")
        (user_node, [account_nodes], [access_nodes]) = row
        logger.debug(f"{user_node=}")
        logger.debug(f"{account_nodes=}")
        logger.debug(f"{access_nodes=}")
        accounts = [
            AccountOut.model_validate(a.__dict__)
            for a in account_nodes
        ]
        accesses = [
            AccessOut.model_validate(ac.__dict__)
            for ac in access_nodes
        ]

        user_data = user_node.__properties__
        user_data["accounts"] = accounts
        user_data["access"] = accesses
        user_list.append(User.model_validate(user_data))

    return user_list


@router.get("/users/{user_uid}")
async def get_user(
    user_uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
) -> User:
    await authorize_api("users_v2", request, jwt)

    site = await get_site_from_request(request)
    try:
        organization = await Organization.objects.aget(site=site)
    except Organization.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found for this site",
        )

    if not organization.neomodel_uid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization does not have a neomodel_uid",
        )

    entry_uid = str(organization.neomodel_uid.hex)

    query = """
    MATCH (u:User {uid: $user_uid})-[:HAS_ACCESS]->(ac:Access {active: true})-[:ACCESS_TO]->(e:Entry {uid: $entry_uid})
    OPTIONAL MATCH (u)-[:HAS_ACCOUNT]->(a:Account)
    RETURN u, collect(DISTINCT a) AS accounts, collect(DISTINCT ac) AS accesses
    """
    results, _ = await adb.cypher_query(
        query, {"user_uid": user_uid, "entry_uid": entry_uid}, resolve_objects=True
    )

    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with uid {user_uid} not found for this site",
        )
    logger.debug(f"{results=}")
    user_node, [account_nodes], [access_nodes] = results[0]

    accounts = [
        AccountOut.model_validate(a.__properties__)
        for a in account_nodes
    ]
    accesses = [
        AccessOut.model_validate(ac.__properties__)
        for ac in access_nodes
    ]

    user_data = user_node.__properties__
    user_data["accounts"] = accounts
    user_data["access"] = accesses
    return User.model_validate(user_data)
