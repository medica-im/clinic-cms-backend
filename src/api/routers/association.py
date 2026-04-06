import logging
from typing import Annotated
from uuid import uuid4
from fastapi import APIRouter, Request, Depends, status, HTTPException
from neomodel import adb
from api.auth import JWT, authorize_api
from api.types.association import (
    OfficerPost,
    OfficerPatch,
    OfficerResponse,
    BoardMemberPost,
    BoardMemberPatch,
    BoardMemberResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def verify_user_access(jwt: dict, entry_uid: str):
    """Verify the requesting user has an active Access for the given Entry."""
    sub = jwt.get("providerAccountId")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No account identifier in JWT"
        )
    query = """
    MATCH (a:Account {sub: $sub})<-[:HAS_ACCOUNT]-(u:User)
          -[:HAS_ACCESS]->(ac:Access {active: true})
          -[:ACCESS_TO]->(e:Entry {uid: $entry_uid})
    RETURN ac.role
    """
    results, _ = await adb.cypher_query(
        query, {"sub": sub, "entry_uid": entry_uid}
    )
    if not results:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this entry"
        )


async def _get_entry_uid_for_node(label: str, uid: str) -> str:
    """Get the entry_uid for an Officer or BoardMember node."""
    query = f"""
    MATCH (n:{label} {{uid: $uid}})-[:MEMBER_OF]->(e:Entry)
    RETURN e.uid
    """
    results, _ = await adb.cypher_query(query, {"uid": uid})
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{label} not found"
        )
    return results[0][0]


# ─── Officer endpoints ───────────────────────────────────────────────


@router.get("/officers")
async def list_officers(
    entry_uid: str,
) -> list[OfficerResponse]:
    query = """
    MATCH (o:Officer)-[:MEMBER_OF]->(e:Entry {uid: $entry_uid})
    MATCH (o)-[:HAS_EFFECTOR]->(eff:Effector)
    MATCH (o)-[rel:HAS_ROLE]->(role:OrganizationRole)
    RETURN o, e.uid AS entry_uid, eff.uid AS effector_uid,
           role.uid AS role_uid, rel.label AS role_label
    """
    results, _ = await adb.cypher_query(
        query, {"entry_uid": entry_uid}, resolve_objects=False
    )
    officers = []
    for row in results:
        props = dict(row[0])
        officers.append(OfficerResponse(
            uid=props["uid"],
            entry_uid=row[1],
            effector_uid=row[2],
            role_uid=row[3],
            role_label=row[4],
            start=str(props.get("start")),
            stop=str(props["stop"]) if props.get("stop") else None,
        ))
    return officers


@router.post("/officers", status_code=status.HTTP_201_CREATED)
async def create_officer(
    item: OfficerPost,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
) -> OfficerResponse:
    await authorize_api("association", request, jwt)
    await verify_user_access(jwt, item.entry_uid)
    query = """
    MATCH (e:Entry {uid: $entry_uid})
    MATCH (eff:Effector {uid: $effector_uid})
    MATCH (role:OrganizationRole {uid: $role_uid})
    CREATE (o:Officer {uid: $uid, start: date($start)})
    CREATE (o)-[:MEMBER_OF]->(e)
    CREATE (o)-[:HAS_EFFECTOR]->(eff)
    CREATE (o)-[rel:HAS_ROLE]->(role)
    SET rel.label = $role_label
    WITH o, e, eff, role, rel
    FOREACH (_ IN CASE WHEN $stop IS NOT NULL THEN [1] ELSE [] END |
        SET o.stop = date($stop)
    )
    RETURN o, e.uid AS entry_uid, eff.uid AS effector_uid,
           role.uid AS role_uid, rel.label AS role_label
    """
    params = {
        "entry_uid": item.entry_uid,
        "effector_uid": item.effector_uid,
        "role_uid": item.role_uid,
        "role_label": item.role_label,
        "uid": uuid4().hex,
        "start": item.start,
        "stop": item.stop,
    }
    results, _ = await adb.cypher_query(query, params, resolve_objects=False)
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry, Effector, or OrganizationRole not found"
        )
    props = dict(results[0][0])
    return OfficerResponse(
        uid=props["uid"],
        entry_uid=results[0][1],
        effector_uid=results[0][2],
        role_uid=results[0][3],
        role_label=results[0][4],
        start=str(props.get("start")),
        stop=str(props["stop"]) if props.get("stop") else None,
    )


@router.patch("/officers/{uid}")
async def update_officer(
    uid: str,
    item: OfficerPatch,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
) -> OfficerResponse:
    await authorize_api("association", request, jwt)
    entry_uid = await _get_entry_uid_for_node("Officer", uid)
    await verify_user_access(jwt, entry_uid)

    fields = item.model_fields_set
    set_clauses = []
    params: dict = {"uid": uid}

    if "start" in fields:
        set_clauses.append("o.start = date($start)")
        params["start"] = item.start
    if "stop" in fields:
        if item.stop is not None:
            set_clauses.append("o.stop = date($stop)")
            params["stop"] = item.stop
        else:
            set_clauses.append("o.stop = null")

    rel_update = ""
    if "role_label" in fields:
        rel_update = """
        WITH o
        MATCH (o)-[rel:HAS_ROLE]->(:OrganizationRole)
        SET rel.label = $role_label
        """
        params["role_label"] = item.role_label

    set_part = f"SET {', '.join(set_clauses)}" if set_clauses else ""
    query = f"""
    MATCH (o:Officer {{uid: $uid}})
    {set_part}
    {rel_update}
    WITH o
    MATCH (o)-[:MEMBER_OF]->(e:Entry)
    MATCH (o)-[:HAS_EFFECTOR]->(eff:Effector)
    MATCH (o)-[rel:HAS_ROLE]->(role:OrganizationRole)
    RETURN o, e.uid AS entry_uid, eff.uid AS effector_uid,
           role.uid AS role_uid, rel.label AS role_label
    """
    results, _ = await adb.cypher_query(query, params, resolve_objects=False)
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Officer not found"
        )
    props = dict(results[0][0])
    return OfficerResponse(
        uid=props["uid"],
        entry_uid=results[0][1],
        effector_uid=results[0][2],
        role_uid=results[0][3],
        role_label=results[0][4],
        start=str(props.get("start")),
        stop=str(props["stop"]) if props.get("stop") else None,
    )


@router.delete("/officers/{uid}")
async def delete_officer(
    uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    await authorize_api("association", request, jwt)
    entry_uid = await _get_entry_uid_for_node("Officer", uid)
    await verify_user_access(jwt, entry_uid)

    query = """
    MATCH (o:Officer {uid: $uid})
    DETACH DELETE o
    RETURN true
    """
    results, _ = await adb.cypher_query(query, {"uid": uid})
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Officer not found"
        )
    return {"message": "Officer deleted", "uid": uid}


# ─── BoardMember endpoints ───────────────────────────────────────────


@router.get("/board-members")
async def list_board_members(
    entry_uid: str,
) -> list[BoardMemberResponse]:
    query = """
    MATCH (bm:BoardMember)-[:MEMBER_OF]->(e:Entry {uid: $entry_uid})
    MATCH (bm)-[:HAS_EFFECTOR]->(eff:Effector)
    RETURN bm, e.uid AS entry_uid, eff.uid AS effector_uid
    """
    results, _ = await adb.cypher_query(
        query, {"entry_uid": entry_uid}, resolve_objects=False
    )
    members = []
    for row in results:
        props = dict(row[0])
        members.append(BoardMemberResponse(
            uid=props["uid"],
            entry_uid=row[1],
            effector_uid=row[2],
            start=str(props.get("start")),
            stop=str(props["stop"]) if props.get("stop") else None,
        ))
    return members


@router.post("/board-members", status_code=status.HTTP_201_CREATED)
async def create_board_member(
    item: BoardMemberPost,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
) -> BoardMemberResponse:
    await authorize_api("association", request, jwt)
    await verify_user_access(jwt, item.entry_uid)
    query = """
    MATCH (e:Entry {uid: $entry_uid})
    MATCH (eff:Effector {uid: $effector_uid})
    CREATE (bm:BoardMember {uid: $uid, start: date($start)})
    CREATE (bm)-[:MEMBER_OF]->(e)
    CREATE (bm)-[:HAS_EFFECTOR]->(eff)
    WITH bm, e, eff
    FOREACH (_ IN CASE WHEN $stop IS NOT NULL THEN [1] ELSE [] END |
        SET bm.stop = date($stop)
    )
    RETURN bm, e.uid AS entry_uid, eff.uid AS effector_uid
    """
    params = {
        "entry_uid": item.entry_uid,
        "effector_uid": item.effector_uid,
        "uid": uuid4().hex,
        "start": item.start,
        "stop": item.stop,
    }
    results, _ = await adb.cypher_query(query, params, resolve_objects=False)
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry or Effector not found"
        )
    props = dict(results[0][0])
    return BoardMemberResponse(
        uid=props["uid"],
        entry_uid=results[0][1],
        effector_uid=results[0][2],
        start=str(props.get("start")),
        stop=str(props["stop"]) if props.get("stop") else None,
    )


@router.patch("/board-members/{uid}")
async def update_board_member(
    uid: str,
    item: BoardMemberPatch,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
) -> BoardMemberResponse:
    await authorize_api("association", request, jwt)
    entry_uid = await _get_entry_uid_for_node("BoardMember", uid)
    await verify_user_access(jwt, entry_uid)

    fields = item.model_fields_set
    set_clauses = []
    params: dict = {"uid": uid}

    if "start" in fields:
        set_clauses.append("bm.start = date($start)")
        params["start"] = item.start
    if "stop" in fields:
        if item.stop is not None:
            set_clauses.append("bm.stop = date($stop)")
            params["stop"] = item.stop
        else:
            set_clauses.append("bm.stop = null")

    set_part = f"SET {', '.join(set_clauses)}" if set_clauses else ""
    query = f"""
    MATCH (bm:BoardMember {{uid: $uid}})
    {set_part}
    WITH bm
    MATCH (bm)-[:MEMBER_OF]->(e:Entry)
    MATCH (bm)-[:HAS_EFFECTOR]->(eff:Effector)
    RETURN bm, e.uid AS entry_uid, eff.uid AS effector_uid
    """
    results, _ = await adb.cypher_query(query, params, resolve_objects=False)
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BoardMember not found"
        )
    props = dict(results[0][0])
    return BoardMemberResponse(
        uid=props["uid"],
        entry_uid=results[0][1],
        effector_uid=results[0][2],
        start=str(props.get("start")),
        stop=str(props["stop"]) if props.get("stop") else None,
    )


@router.delete("/board-members/{uid}")
async def delete_board_member(
    uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    await authorize_api("association", request, jwt)
    entry_uid = await _get_entry_uid_for_node("BoardMember", uid)
    await verify_user_access(jwt, entry_uid)

    query = """
    MATCH (bm:BoardMember {uid: $uid})
    DETACH DELETE bm
    RETURN true
    """
    results, _ = await adb.cypher_query(query, {"uid": uid})
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BoardMember not found"
        )
    return {"message": "BoardMember deleted", "uid": uid}
