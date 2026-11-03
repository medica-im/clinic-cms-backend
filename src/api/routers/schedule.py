import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from api.auth import JWT, authorize_api, check_cookie_jwt
from api.graph import read, write
from api.types.schedule import (
    Schedule,
    SchedulePost,
    SchedulePut,
    node_properties,
    schedule_from_node,
)
from api.utils import get_entry, get_entry_users

router = APIRouter()

ENDPOINT = "schedules_v2"


async def authorize_write(entry_uid: str, request: Request, jwt: dict) -> None:
    entry = await get_entry(entry_uid)
    users = await get_entry_users(entry)
    await authorize_api(ENDPOINT, request, jwt, users=users)


async def entry_of(schedule_uid: str) -> str:
    rows = await read(
        "MATCH (e:Entry)-[:HAS_SCHEDULE]->(:Schedule {uid: $uid}) RETURN e.uid AS entry",
        uid=schedule_uid,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return rows[0]["entry"]


@router.post("/schedules", response_model=Schedule)
async def create_item(item: SchedulePost, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_write(item.entry, request, jwt)
    rows = await write(
        """
        MATCH (e:Entry {uid: $entry})
        CREATE (e)-[:HAS_SCHEDULE]->(s:Schedule {uid: $uid})
        SET s += $props
        RETURN properties(s) AS s
        """,
        entry=item.entry,
        uid=uuid.uuid4().hex,
        props=node_properties(item),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Entry not found")
    return schedule_from_node(item.entry, rows[0]["s"])


@router.put("/schedules/{item_uid}", response_model=Schedule)
async def update_item(item_uid: str, item: SchedulePut, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    entry_uid = await entry_of(item_uid)
    await authorize_write(entry_uid, request, jwt)
    if item.entry != entry_uid:
        raise HTTPException(status_code=400, detail="A schedule cannot move to another entry")
    rows = await write(
        "MATCH (s:Schedule {uid: $uid}) SET s += $props RETURN properties(s) AS s",
        uid=item_uid,
        props=node_properties(item),
    )
    return schedule_from_node(entry_uid, rows[0]["s"])


@router.delete("/schedules/{item_uid}")
async def delete_item(item_uid: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    entry_uid = await entry_of(item_uid)
    await authorize_write(entry_uid, request, jwt)
    await write("MATCH (s:Schedule {uid: $uid}) DETACH DELETE s", uid=item_uid)


@router.get("/entries/{entry_uid}/schedules", response_model=list[Schedule])
async def list_items(entry_uid: str, request: Request, jwt: Annotated[dict | None, Depends(check_cookie_jwt)]):
    await authorize_api(ENDPOINT, request, jwt)
    rows = await read(
        """
        MATCH (e:Entry {uid: $entry})
        OPTIONAL MATCH (e)-[:HAS_SCHEDULE]->(s:Schedule)
        RETURN properties(s) AS s ORDER BY s.channel, s.label
        """,
        entry=entry_uid,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Entry not found")
    return [schedule_from_node(entry_uid, row["s"]) for row in rows if row["s"] is not None]
