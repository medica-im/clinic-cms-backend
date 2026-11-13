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

# A node read with its parent and its links, by slug. A target with no slug (an
# older node never adopted) is left out.
PROJECTION = """
    OPTIONAL MATCH (c)-[:PART_OF]->(p:Condition)
    RETURN properties(c) AS c, p.slug AS parent,
        [(c)-[:MAY_LEAD_TO]->(t) WHERE (t:Situation OR t:Condition) AND t.slug IS NOT NULL | t.slug] AS may_lead_to,
        [(c)-[:IMPACTS]->(n:Need) WHERE n.slug IS NOT NULL | n.slug] AS impacts
"""

# Each list sent replaces the links of its kind; a list not sent leaves them alone.
REPLACE_LINKS = """
    MATCH (c:Condition {slug: $slug})
    CALL {
        WITH c
        WITH c WHERE $set_may_lead_to
        OPTIONAL MATCH (c)-[old:MAY_LEAD_TO]->()
        DELETE old
        WITH DISTINCT c
        UNWIND $may_lead_to AS target
        MATCH (t {slug: target}) WHERE t:Situation OR t:Condition
        CREATE (c)-[:MAY_LEAD_TO]->(t)
    }
    CALL {
        WITH c
        WITH c WHERE $set_impacts
        OPTIONAL MATCH (c)-[old:IMPACTS]->(:Need)
        DELETE old
        WITH DISTINCT c
        UNWIND $impacts AS target
        MATCH (n:Need {slug: target})
        CREATE (c)-[:IMPACTS]->(n)
    }
    RETURN c.slug AS slug
"""


def from_row(row) -> Condition:
    return condition_from_row(row["c"], row["parent"], row["may_lead_to"], row["impacts"])


async def exists(slug: str) -> bool:
    return bool(await read("MATCH (c:Condition {slug: $slug}) RETURN c.slug AS slug", slug=slug))


async def check_links(may_lead_to: list[str] | None, impacts: list[str] | None) -> None:
    """422 naming every target that is not a situation or condition (may_lead_to) or a need (impacts)."""
    may_lead_to, impacts = may_lead_to or [], impacts or []
    rows = await read(
        """
        OPTIONAL MATCH (t) WHERE (t:Situation OR t:Condition) AND t.slug IN $may_lead_to
        WITH collect(DISTINCT t.slug) AS leads
        OPTIONAL MATCH (n:Need) WHERE n.slug IN $impacts
        RETURN leads, collect(DISTINCT n.slug) AS needs
        """,
        may_lead_to=may_lead_to,
        impacts=impacts,
    )
    leads, needs = set(rows[0]["leads"]), set(rows[0]["needs"])
    unknown = [f"may_lead_to {s}" for s in may_lead_to if s not in leads] + [f"impacts {s}" for s in impacts if s not in needs]
    if unknown:
        raise HTTPException(status_code=422, detail={"code": "unknown_target", "targets": unknown})


async def replace_links(slug: str, item, sent: set[str]) -> None:
    if not sent & {"may_lead_to", "impacts"}:
        return
    await write(
        REPLACE_LINKS,
        slug=slug,
        set_may_lead_to="may_lead_to" in sent,
        may_lead_to=item.may_lead_to or [],
        set_impacts="impacts" in sent,
        impacts=item.impacts or [],
    )


async def one(slug: str) -> Condition:
    rows = await read("MATCH (c:Condition {slug: $slug})" + PROJECTION, slug=slug)
    return from_row(rows[0])


@router.get("/conditions", response_model=list[Condition])
async def list_items(request: Request, jwt: Annotated[dict | None, Depends(check_cookie_jwt)]):
    await authorize_api(ENDPOINT, request, jwt)
    rows = await read(
        "MATCH (c:Condition)" + PROJECTION
        + " ORDER BY coalesce(c.chapter, 99), CASE c.kind WHEN 'chapter' THEN 0 ELSE 1 END, c.slug"
    )
    return [from_row(row) for row in rows]


@router.get("/conditions/{slug}", response_model=Condition)
async def get_item(slug: str, request: Request, jwt: Annotated[dict | None, Depends(check_cookie_jwt)]):
    await authorize_api(ENDPOINT, request, jwt)
    rows = await read("MATCH (c:Condition {slug: $slug})" + PROJECTION, slug=slug)
    if not rows:
        raise HTTPException(status_code=404, detail="Condition not found")
    return from_row(rows[0])


@router.post("/conditions", response_model=Condition, status_code=status.HTTP_201_CREATED)
async def create_item(item: ConditionPost, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api(ENDPOINT, request, jwt)
    if await exists(item.slug):
        raise HTTPException(status_code=409, detail="A condition already has this slug")
    if item.parent is not None and not await exists(item.parent):
        raise HTTPException(status_code=422, detail=f"Unknown parent: {item.parent}")
    await check_links(item.may_lead_to, item.impacts)
    await write(
        """
        CREATE (c:Condition {uid: $uid})
        SET c += $props
        FOREACH (_ IN CASE WHEN c.kind = 'chapter' THEN [1] ELSE [] END | SET c:Chapter)
        WITH c
        OPTIONAL MATCH (p:Condition {slug: $parent})
        FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | CREATE (c)-[:PART_OF]->(p))
        RETURN c.slug AS slug
        """,
        uid=uuid.uuid4().hex,
        props=node_properties(item),
        parent=item.parent,
    )
    await replace_links(item.slug, item, {"may_lead_to", "impacts"})
    return await one(item.slug)


@router.patch("/conditions/{slug}", response_model=Condition)
async def patch_item(slug: str, item: ConditionPatch, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api(ENDPOINT, request, jwt)
    current = await read(
        "MATCH (c:Condition {slug: $slug}) OPTIONAL MATCH (c)-[:PART_OF]->(p:Condition) RETURN c.kind AS kind, p.slug AS parent",
        slug=slug,
    )
    if not current:
        raise HTTPException(status_code=404, detail="Condition not found")
    sent = item.model_fields_set
    change_parent = "parent" in sent
    kind = item.kind if "kind" in sent else current[0]["kind"]
    parent = item.parent if change_parent else current[0]["parent"]
    if kind == "chapter" and parent is not None:
        raise HTTPException(status_code=409, detail="A chapter has no parent")
    if "may_lead_to" in sent and slug in item.may_lead_to:
        raise HTTPException(status_code=422, detail="A condition cannot lead to itself")
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
    await check_links(item.may_lead_to if "may_lead_to" in sent else [], item.impacts if "impacts" in sent else [])
    await write(
        """
        MATCH (c:Condition {slug: $slug})
        SET c += $props
        FOREACH (_ IN CASE WHEN c.kind = 'chapter' THEN [1] ELSE [] END | SET c:Chapter)
        FOREACH (_ IN CASE WHEN c.kind = 'chapter' THEN [] ELSE [1] END | REMOVE c:Chapter)
        WITH c
        OPTIONAL MATCH (c)-[old:PART_OF]->(:Condition)
        FOREACH (_ IN CASE WHEN $change_parent THEN [1] ELSE [] END | DELETE old)
        WITH c
        OPTIONAL MATCH (p:Condition {slug: $parent})
        FOREACH (_ IN CASE WHEN $change_parent AND p IS NOT NULL THEN [1] ELSE [] END | CREATE (c)-[:PART_OF]->(p))
        RETURN c.slug AS slug
        """,
        slug=slug,
        props={name: getattr(item, name) for name in PROPERTIES if name in sent},
        change_parent=change_parent,
        parent=item.parent,
    )
    await replace_links(slug, item, sent)
    return await one(slug)
