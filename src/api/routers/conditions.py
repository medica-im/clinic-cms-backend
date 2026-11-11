import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.auth import JWT, authorize_api, check_cookie_jwt
from api.graph import read, write
from api.types.condition import (
    PROPERTIES,
    Condition,
    ConditionPatch,
    ConditionPost,
    condition_from_row,
    node_properties,
)

router = APIRouter()

ENDPOINT = "conditions_v2"


async def exists(slug: str) -> bool:
    return bool(await read("MATCH (c:Condition {slug: $slug}) RETURN c.slug AS slug", slug=slug))


@router.get("/conditions", response_model=list[Condition])
async def list_items(request: Request, jwt: Annotated[dict | None, Depends(check_cookie_jwt)]):
    await authorize_api(ENDPOINT, request, jwt)
    rows = await read(
        """
        MATCH (c:Condition)
        OPTIONAL MATCH (c)-[:PART_OF]->(p:Condition)
        RETURN properties(c) AS c, p.slug AS parent
        ORDER BY coalesce(c.chapter, 99), CASE c.kind WHEN 'chapter' THEN 0 ELSE 1 END, c.slug
        """
    )
    return [condition_from_row(row["c"], row["parent"]) for row in rows]


@router.get("/conditions/{slug}", response_model=Condition)
async def get_item(slug: str, request: Request, jwt: Annotated[dict | None, Depends(check_cookie_jwt)]):
    await authorize_api(ENDPOINT, request, jwt)
    rows = await read(
        """
        MATCH (c:Condition {slug: $slug})
        OPTIONAL MATCH (c)-[:PART_OF]->(p:Condition)
        RETURN properties(c) AS c, p.slug AS parent
        """,
        slug=slug,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Condition not found")
    return condition_from_row(rows[0]["c"], rows[0]["parent"])


@router.post("/conditions", response_model=Condition, status_code=status.HTTP_201_CREATED)
async def create_item(item: ConditionPost, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api(ENDPOINT, request, jwt)
    if await exists(item.slug):
        raise HTTPException(status_code=409, detail="A condition already has this slug")
    if item.parent is not None and not await exists(item.parent):
        raise HTTPException(status_code=422, detail=f"Unknown parent: {item.parent}")
    rows = await write(
        """
        CREATE (c:Condition {uid: $uid})
        SET c += $props
        WITH c
        OPTIONAL MATCH (p:Condition {slug: $parent})
        FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | CREATE (c)-[:PART_OF]->(p))
        RETURN properties(c) AS c, p.slug AS parent
        """,
        uid=uuid.uuid4().hex,
        props=node_properties(item),
        parent=item.parent,
    )
    return condition_from_row(rows[0]["c"], rows[0]["parent"])


@router.patch("/conditions/{slug}", response_model=Condition)
async def patch_item(slug: str, item: ConditionPatch, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api(ENDPOINT, request, jwt)
    if not await exists(slug):
        raise HTTPException(status_code=404, detail="Condition not found")
    sent = item.model_fields_set
    change_parent = "parent" in sent
    if change_parent and item.parent is not None:
        if not await exists(item.parent):
            raise HTTPException(status_code=422, detail=f"Unknown parent: {item.parent}")
        loop = await read(
            "MATCH (p:Condition {slug: $parent})-[:PART_OF*0..]->(c:Condition {slug: $slug}) RETURN count(p) AS n",
            parent=item.parent,
            slug=slug,
        )
        if loop[0]["n"]:
            raise HTTPException(status_code=409, detail="That parent would make the tree loop")
    rows = await write(
        """
        MATCH (c:Condition {slug: $slug})
        SET c += $props
        WITH c
        OPTIONAL MATCH (c)-[old:PART_OF]->(:Condition)
        FOREACH (_ IN CASE WHEN $change_parent THEN [1] ELSE [] END | DELETE old)
        WITH c
        OPTIONAL MATCH (p:Condition {slug: $parent})
        FOREACH (_ IN CASE WHEN $change_parent AND p IS NOT NULL THEN [1] ELSE [] END | CREATE (c)-[:PART_OF]->(p))
        WITH c
        OPTIONAL MATCH (c)-[:PART_OF]->(q:Condition)
        RETURN properties(c) AS c, q.slug AS parent
        """,
        slug=slug,
        props={name: getattr(item, name) for name in PROPERTIES if name in sent},
        change_parent=change_parent,
        parent=item.parent,
    )
    return condition_from_row(rows[0]["c"], rows[0]["parent"])
