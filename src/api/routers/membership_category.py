import logging
from typing import Annotated
from uuid import uuid4
from fastapi import APIRouter, Request, Depends, status, HTTPException
from neomodel import adb
from api.auth import JWT, authorize_api, verify_user_access
from api.types.membership_category import (
    MembershipCategoryPost,
    MembershipCategoryPatch,
    MembershipCategoryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/membership-categories")
async def list_membership_categories(
    entry_uid: str,
) -> list[MembershipCategoryResponse]:
    query = """
    MATCH (mc:MembershipCategory)-[:CATEGORY_OF]->(e:Entry {uid: $entry_uid})
    RETURN mc, e.uid AS entry_uid
    """
    results, _ = await adb.cypher_query(
        query, {"entry_uid": entry_uid}, resolve_objects=False
    )
    return [
        MembershipCategoryResponse(
            uid=dict(row[0])["uid"],
            entry_uid=row[1],
            label=dict(row[0]).get("label"),
        )
        for row in results
    ]


@router.post("/membership-categories", status_code=status.HTTP_201_CREATED)
async def create_membership_category(
    item: MembershipCategoryPost,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
) -> MembershipCategoryResponse:
    await authorize_api("association", request, jwt)
    await verify_user_access(jwt, item.entry_uid)
    uid = uuid4().hex
    query = """
    MATCH (e:Entry {uid: $entry_uid})
    CREATE (mc:MembershipCategory {uid: $uid, label: $label})
    CREATE (mc)-[:CATEGORY_OF]->(e)
    RETURN mc, e.uid AS entry_uid
    """
    results, _ = await adb.cypher_query(
        query,
        {"entry_uid": item.entry_uid, "uid": uid, "label": item.label},
        resolve_objects=False,
    )
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found"
        )
    props = dict(results[0][0])
    return MembershipCategoryResponse(
        uid=props["uid"], entry_uid=results[0][1], label=props.get("label")
    )


@router.patch("/membership-categories/{uid}")
async def update_membership_category(
    uid: str,
    item: MembershipCategoryPatch,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
) -> MembershipCategoryResponse:
    await authorize_api("association", request, jwt)
    entry_uid = await _get_entry_uid(uid)
    await verify_user_access(jwt, entry_uid)

    fields = item.model_fields_set
    set_clauses = []
    params: dict = {"uid": uid}

    if "label" in fields:
        set_clauses.append("mc.label = $label")
        params["label"] = item.label

    set_part = f"SET {', '.join(set_clauses)}" if set_clauses else ""
    query = f"""
    MATCH (mc:MembershipCategory {{uid: $uid}})-[:CATEGORY_OF]->(e:Entry)
    {set_part}
    RETURN mc, e.uid AS entry_uid
    """
    results, _ = await adb.cypher_query(query, params, resolve_objects=False)
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MembershipCategory not found"
        )
    props = dict(results[0][0])
    return MembershipCategoryResponse(
        uid=props["uid"], entry_uid=results[0][1], label=props.get("label")
    )


@router.delete("/membership-categories/{uid}")
async def delete_membership_category(
    uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    await authorize_api("association", request, jwt)
    entry_uid = await _get_entry_uid(uid)
    await verify_user_access(jwt, entry_uid)

    check_query = """
    MATCH (bm:BoardMember)-[:HAS_MEMBERSHIP_CATEGORY]->(mc:MembershipCategory {uid: $uid})
    RETURN count(bm) AS member_count
    """
    results, _ = await adb.cypher_query(check_query, {"uid": uid})
    if results and results[0][0] > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete: linked to one or more BoardMembers"
        )

    delete_query = """
    MATCH (mc:MembershipCategory {uid: $uid})
    DETACH DELETE mc
    RETURN true
    """
    results, _ = await adb.cypher_query(delete_query, {"uid": uid})
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MembershipCategory not found"
        )
    return {"message": "MembershipCategory deleted", "uid": uid}


async def _get_entry_uid(category_uid: str) -> str:
    """Get the entry_uid for a MembershipCategory."""
    query = """
    MATCH (mc:MembershipCategory {uid: $uid})-[:CATEGORY_OF]->(e:Entry)
    RETURN e.uid
    """
    results, _ = await adb.cypher_query(query, {"uid": category_uid})
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MembershipCategory not found"
        )
    return results[0][0]
