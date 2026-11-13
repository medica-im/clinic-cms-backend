import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from neo4j.exceptions import ConstraintError

from api.auth import JWT, authorize_api, check_cookie_jwt
from api.graph import read, write
from api.types.need_node import NEED_PROPERTIES, NeedNode, NeedPatch, NeedPost, need_from_row
from api.types.situation import SlugBody

router = APIRouter()

ENDPOINT = "needs_v2"

# One row per need, with every parent: by slug (those that have one) and by uid.
PROJECTION = """
    RETURN properties(n) AS n,
        [(n)-[:PART_OF]->(p:Need) WHERE p.slug IS NOT NULL | p.slug] AS parents,
        [(n)-[:PART_OF]->(p:Need) | p.uid] AS parent_uids
"""

# The parent edges are replaced only when the body sent them.
REPLACE_PARENTS = """
    CALL {
        WITH n
        WITH n WHERE $set_parents
        OPTIONAL MATCH (n)-[old:PART_OF]->(:Need)
        DELETE old
        WITH DISTINCT n
        UNWIND $parents AS slug
        MATCH (p:Need {slug: slug})
        CREATE (n)-[:PART_OF]->(p)
    }
    WITH n
"""


async def exists(slug: str) -> bool:
    return bool(await read("MATCH (n:Need {slug: $slug}) RETURN n.slug AS slug", slug=slug))


async def check_parents(parents: list[str]) -> None:
    rows = await read(
        "UNWIND $slugs AS slug OPTIONAL MATCH (n:Need {slug: slug}) WITH slug WHERE n IS NULL RETURN slug",
        slugs=parents,
    )
    if rows:
        raise HTTPException(status_code=422, detail={"code": "unknown_target", "slugs": sorted(r["slug"] for r in rows)})


@router.get("/needs/tree", response_model=list[NeedNode])
async def list_items(request: Request, jwt: Annotated[dict | None, Depends(check_cookie_jwt)]):
    await authorize_api(ENDPOINT, request, jwt)
    rows = await read("MATCH (n:Need)" + PROJECTION + " ORDER BY n.slug IS NULL, n.slug, n.name_fr")
    return [need_from_row(row) for row in rows]


@router.get("/needs/{slug}", response_model=NeedNode)
async def get_item(slug: str, request: Request, jwt: Annotated[dict | None, Depends(check_cookie_jwt)]):
    await authorize_api(ENDPOINT, request, jwt)
    rows = await read("MATCH (n:Need {slug: $slug})" + PROJECTION, slug=slug)
    if not rows:
        raise HTTPException(status_code=404, detail="Need not found")
    return need_from_row(rows[0])


@router.post("/needs", response_model=NeedNode, status_code=status.HTTP_201_CREATED)
async def create_item(item: NeedPost, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api(ENDPOINT, request, jwt)
    if await exists(item.slug):
        raise HTTPException(status_code=409, detail="A need already has this slug")
    await check_parents(item.parents)
    try:
        rows = await write(
            "CREATE (n:Need {uid: $uid}) SET n += $props WITH n" + REPLACE_PARENTS + PROJECTION,
            uid=uuid.uuid4().hex,
            props={"slug": item.slug, **{name: getattr(item, name) for name in NEED_PROPERTIES}},
            set_parents=True,
            parents=item.parents,
        )
    except ConstraintError:
        raise HTTPException(status_code=409, detail="A need already has this name")
    return need_from_row(rows[0])


@router.patch("/needs/by-uid/{uid}", response_model=NeedNode)
async def give_slug(uid: str, item: SlugBody, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    """Give a slug to a need that predates it: once, never a rename."""
    await authorize_api(ENDPOINT, request, jwt)
    found = await read("MATCH (n:Need {uid: $uid}) RETURN n.slug AS slug", uid=uid)
    if not found:
        raise HTTPException(status_code=404, detail="Need not found")
    if found[0]["slug"] is not None:
        raise HTTPException(status_code=409, detail="This need already has a slug")
    if await exists(item.slug):
        raise HTTPException(status_code=409, detail="A need already has this slug")
    rows = await write(
        "MATCH (n:Need {uid: $uid}) WHERE n.slug IS NULL SET n.slug = $slug WITH n" + PROJECTION,
        uid=uid,
        slug=item.slug,
    )
    return need_from_row(rows[0])


@router.patch("/needs/{slug}", response_model=NeedNode)
async def patch_item(slug: str, item: NeedPatch, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api(ENDPOINT, request, jwt)
    if not await exists(slug):
        raise HTTPException(status_code=404, detail="Need not found")
    sent = item.model_fields_set
    if "parents" in sent and item.parents:
        await check_parents(item.parents)
        loop = await read(
            "MATCH (p:Need)-[:PART_OF*0..]->(n:Need {slug: $slug}) WHERE p.slug IN $parents RETURN count(p) AS n",
            parents=item.parents,
            slug=slug,
        )
        if loop[0]["n"]:
            raise HTTPException(status_code=409, detail="That parent would make the graph loop")
    try:
        rows = await write(
            "MATCH (n:Need {slug: $slug}) SET n += $props WITH n" + REPLACE_PARENTS + PROJECTION,
            slug=slug,
            props={name: getattr(item, name) for name in NEED_PROPERTIES if name in sent},
            set_parents="parents" in sent,
            parents=item.parents or [],
        )
    except ConstraintError:
        raise HTTPException(status_code=409, detail="A need already has this name")
    return need_from_row(rows[0])
