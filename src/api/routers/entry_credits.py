"""Who a page credits: its team, retired members included.

See tests/api/test_entry_credits.py for the rules and why.
"""
from types import SimpleNamespace
from typing import Annotated

from django.conf import settings
from fastapi import APIRouter, Depends, Query, Request

from api.auth import check_cookie_jwt
from api.graph import read
from api.neo4j_auth import get_neo4j_role, normalize_neo4j_role
from api.types.entry_credit import EntryCredit
from api.utils import ALLOWED_ACCESS, get_directory, scrub_avatar
from directory.utils import async_flex_effector_type_label, async_get_avatar_url

router = APIRouter()

MAX_SLUGS = 50

CREDITS = """
UNWIND range(0, size($slugs) - 1) AS position
MATCH (:Directory {name: $directory})-[:HAS_ENTRY]->(e:Entry {slug: $slugs[position]})
MATCH (e)-[:HAS_EFFECTOR]->(person:Effector)
MATCH (e)-[:HAS_EFFECTOR_TYPE]->(type:EffectorType)
OPTIONAL MATCH (e)-[:HAS_FACILITY]->(facility:Facility)
OPTIONAL MATCH (person)-[location:LOCATION]->(facility)
WITH position, e,
     head(collect(person)) AS person, head(collect(type)) AS type,
     head(collect(facility)) AS facility, head(collect(location)) AS location
RETURN e.slug AS slug, e.uid AS entry_uid, e.active AS active, e.access AS access,
       person.uid AS person_uid, coalesce(person[$name], person.name_fr) AS name, person.gender AS gender,
       type.uid AS type_uid, coalesce(type[$name], type.name_fr) AS type_name,
       coalesce(type[$label], type.label_fr) AS type_label,
       facility.uid AS facility_uid, location.uid AS location_uid
ORDER BY position
"""


def _node(uid: str | None):
    return SimpleNamespace(uid=uid) if uid else None


@router.get("/entry-credits")
async def entry_credits(
    req: Request,
    jwt: Annotated[dict, Depends(check_cookie_jwt)],
    slug: Annotated[list[str], Query(max_length=MAX_SLUGS)] = [],
) -> list[EntryCredit]:
    if not slug:
        return []
    directory = await get_directory(req)
    role = normalize_neo4j_role(await get_neo4j_role(jwt, directory.site))
    allowed = ALLOWED_ACCESS.get(role)
    language = settings.LANGUAGE_CODE
    rows = await read(
        CREDITS, slugs=slug, directory=directory.name, name=f"name_{language}", label=f"label_{language}"
    )
    credits = []
    for row in rows:
        if allowed is not None and (row["access"] or "anonymous") not in allowed:
            continue
        active = row["active"] is not False
        item = {"avatar": None}
        if active:
            item["avatar"] = await async_get_avatar_url(
                _node(row["entry_uid"]), _node(row["person_uid"]), _node(row["location_uid"]), _node(row["facility_uid"])
            )
            scrub_avatar(item, role)
        label = await async_flex_effector_type_label(
            SimpleNamespace(gender=row["gender"]), SimpleNamespace(uid=row["type_uid"])
        )
        credits.append(
            EntryCredit(
                entrySlug=row["slug"],
                name=row["name"],
                effector_type={"name": row["type_name"], "label": label or row["type_label"] or row["type_name"]},
                active=active,
                avatar=item["avatar"],
            )
        )
    return credits
