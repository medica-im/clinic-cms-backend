import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from neo4j.exceptions import ConstraintError

from api.auth import JWT, authorize_api, check_cookie_jwt
from api.graph import read, write
from api.types.situation import (
    SITUATION_PROPERTIES,
    SituationNode,
    SituationPatch,
    SituationPost,
    SlugBody,
    situation_from_row,
)

router = APIRouter()

ENDPOINT = "situations_v2"

# Legacy data can have a situation under several parents. It is one row, under the
# parent that sorts first by name; `parent_uids` lists them all.
PROJECTION = """
    OPTIONAL MATCH (s)-[:PART_OF]->(p:Situation)
    WITH s, p ORDER BY p.name_fr, p.uid
    WITH s, collect(p) AS parents
    RETURN properties(s) AS s, head(parents).slug AS parent, head(parents).uid AS parent_uid,
        [p IN parents | p.uid] AS parent_uids,
        [(s)-[:MAY_LEAD_TO]->(t:Situation) | t.uid] AS may_lead_to_uids,
        [(s)-[:IMPACTS]->(n:Need) | n.uid] AS impacts_uids,
        [(s)-[:MAY_LEAD_TO]->(t:Situation) WHERE t.slug IS NOT NULL | t.slug] AS may_lead_to,
        [(s)-[:IMPACTS]->(n:Need) WHERE n.slug IS NOT NULL | n.slug] AS impacts
"""

# Each edge kind is replaced only when its flag says the body sent it.
REPLACE_EDGES = """
    CALL {
        WITH s
        WITH s WHERE $set_parent
        OPTIONAL MATCH (s)-[old:PART_OF]->(:Situation)
        DELETE old
        WITH DISTINCT s
        MATCH (p:Situation {slug: $parent})
        CREATE (s)-[:PART_OF]->(p)
    }
    CALL {
        WITH s
        WITH s WHERE $set_may_lead_to
        OPTIONAL MATCH (s)-[old:MAY_LEAD_TO]->(:Situation)
        DELETE old
        WITH DISTINCT s
        UNWIND $may_lead_to AS slug
        MATCH (t:Situation {slug: slug})
        CREATE (s)-[:MAY_LEAD_TO]->(t)
    }
    CALL {
        WITH s
        WITH s WHERE $set_impacts
        OPTIONAL MATCH (s)-[old:IMPACTS]->(:Need)
        DELETE old
        WITH DISTINCT s
        UNWIND $impacts AS slug
        MATCH (n:Need {slug: slug})
        CREATE (s)-[:IMPACTS]->(n)
    }
    WITH s
"""


async def exists(slug: str) -> bool:
    return bool(await read("MATCH (s:Situation {slug: $slug}) RETURN s.slug AS slug", slug=slug))


async def check_targets(parent: str | None, may_lead_to: list[str], impacts: list[str]) -> None:
    """Refuse, before anything is written, any slug that names no node."""
    rows = await read(
        """
        UNWIND $situations AS slug
        OPTIONAL MATCH (s:Situation {slug: slug})
        WITH slug WHERE s IS NULL
        RETURN slug
        UNION
        UNWIND $needs AS slug
        OPTIONAL MATCH (n:Need {slug: slug})
        WITH slug WHERE n IS NULL
        RETURN slug
        """,
        situations=[*([parent] if parent else []), *may_lead_to],
        needs=impacts,
    )
    if rows:
        raise HTTPException(
            status_code=422, detail={"code": "unknown_target", "slugs": sorted(row["slug"] for row in rows)}
        )


def edge_params(item, sent: set[str]) -> dict:
    return {
        "set_parent": "parent" in sent,
        "parent": item.parent,
        "set_may_lead_to": "may_lead_to" in sent,
        "may_lead_to": item.may_lead_to or [],
        "set_impacts": "impacts" in sent,
        "impacts": item.impacts or [],
    }


@router.get("/situations/tree", response_model=list[SituationNode])
async def list_items(request: Request, jwt: Annotated[dict | None, Depends(check_cookie_jwt)]):
    await authorize_api(ENDPOINT, request, jwt)
    rows = await read(
        "MATCH (s:Situation)" + PROJECTION + " ORDER BY s.slug IS NULL, s.slug, s.name_fr"
    )
    return [situation_from_row(row) for row in rows]


@router.get("/situations/{slug}", response_model=SituationNode)
async def get_item(slug: str, request: Request, jwt: Annotated[dict | None, Depends(check_cookie_jwt)]):
    await authorize_api(ENDPOINT, request, jwt)
    rows = await read("MATCH (s:Situation {slug: $slug})" + PROJECTION, slug=slug)
    if not rows:
        raise HTTPException(status_code=404, detail="Situation not found")
    return situation_from_row(rows[0])


@router.post("/situations", response_model=SituationNode, status_code=status.HTTP_201_CREATED)
async def create_item(item: SituationPost, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api(ENDPOINT, request, jwt)
    if await exists(item.slug):
        raise HTTPException(status_code=409, detail="A situation already has this slug")
    await check_targets(item.parent, item.may_lead_to, item.impacts)
    try:
        rows = await write(
            "CREATE (s:Situation {uid: $uid}) SET s += $props WITH s" + REPLACE_EDGES + PROJECTION,
            uid=uuid.uuid4().hex,
            props={"slug": item.slug, **{name: getattr(item, name) for name in SITUATION_PROPERTIES}},
            **edge_params(item, {"parent", "may_lead_to", "impacts"}),
        )
    except ConstraintError:
        raise HTTPException(status_code=409, detail="A situation already has this name")
    return situation_from_row(rows[0])


@router.patch("/situations/by-uid/{uid}", response_model=SituationNode)
async def give_slug(uid: str, item: SlugBody, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    """Give a slug to a situation that predates it: once, never a rename."""
    await authorize_api(ENDPOINT, request, jwt)
    found = await read("MATCH (s:Situation {uid: $uid}) RETURN s.slug AS slug", uid=uid)
    if not found:
        raise HTTPException(status_code=404, detail="Situation not found")
    if found[0]["slug"] is not None:
        raise HTTPException(status_code=409, detail="This situation already has a slug")
    if await exists(item.slug):
        raise HTTPException(status_code=409, detail="A situation already has this slug")
    rows = await write(
        "MATCH (s:Situation {uid: $uid}) WHERE s.slug IS NULL SET s.slug = $slug WITH s" + PROJECTION,
        uid=uid,
        slug=item.slug,
    )
    return situation_from_row(rows[0])


@router.patch("/situations/{slug}", response_model=SituationNode)
async def patch_item(slug: str, item: SituationPatch, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api(ENDPOINT, request, jwt)
    if not await exists(slug):
        raise HTTPException(status_code=404, detail="Situation not found")
    sent = item.model_fields_set
    if "may_lead_to" in sent and slug in item.may_lead_to:
        raise HTTPException(status_code=422, detail="A situation cannot lead to itself")
    await check_targets(
        item.parent if "parent" in sent else None,
        item.may_lead_to if "may_lead_to" in sent else [],
        item.impacts if "impacts" in sent else [],
    )
    if "parent" in sent and item.parent is not None:
        loop = await read(
            "MATCH (p:Situation {slug: $parent})-[:PART_OF*0..]->(s:Situation {slug: $slug}) RETURN count(p) AS n",
            parent=item.parent,
            slug=slug,
        )
        if loop[0]["n"]:
            raise HTTPException(status_code=409, detail="That parent would make the tree loop")
    try:
        rows = await write(
            "MATCH (s:Situation {slug: $slug}) SET s += $props WITH s" + REPLACE_EDGES + PROJECTION,
            slug=slug,
            props={name: getattr(item, name) for name in SITUATION_PROPERTIES if name in sent},
            **edge_params(item, sent),
        )
    except ConstraintError:
        raise HTTPException(status_code=409, detail="A situation already has this name")
    return situation_from_row(rows[0])
