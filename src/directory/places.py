"""The places an entry may cover, found by a few typed letters (tests/api/test_places.py).

Matched on the slugs, which are slugify()'d names: accents, case and apostrophes do not
matter. A département is also found by its code; a region never is, its INSEE code
collides with the départements'. A commune comes with its département's code, the only
way to tell the six Saint-Maurice apart.
"""
from django.utils.text import slugify

from api.graph import read

#: Widest first, among places that match as well.
KINDS = ("country", "region", "department", "commune")
LIMIT = 20

WIDE = """
MATCH (t) WHERE (t:Country OR t:RegionOfFrance OR t:DepartmentOfFrance)
  AND (t.slug CONTAINS $slug OR (t:DepartmentOfFrance AND t.code = $code))
RETURN t.uid AS uid, t.name AS name, t.code AS code, null AS department,
       CASE WHEN t:Country THEN 'country' WHEN t:RegionOfFrance THEN 'region' ELSE 'department' END AS kind,
       CASE WHEN t.slug = $slug OR (t:DepartmentOfFrance AND t.code = $code) THEN 0
            WHEN t.slug STARTS WITH $slug THEN 1 ELSE 2 END AS rank
"""

COMMUNES = """
MATCH (c:Commune) WHERE c.slug_fr CONTAINS $slug
OPTIONAL MATCH (c)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(d:DepartmentOfFrance)
WITH c, d, CASE WHEN c.slug_fr = $slug THEN 0 WHEN c.slug_fr STARTS WITH $slug THEN 1 ELSE 2 END AS rank
RETURN c.uid AS uid, c.name_fr AS name, null AS code, d.code AS department, 'commune' AS kind, rank
ORDER BY rank, name, department
LIMIT $limit
"""


async def search_places(text: str, limit: int = LIMIT) -> list[dict]:
    """At most `limit` places matching `text`, best match first, then the widest."""
    slug = slugify(text or "")
    if len(slug) < 2:
        return []
    params = {"slug": slug, "code": slug.upper(), "limit": limit}
    rows = await read(WIDE, **params) + await read(COMMUNES, **params)
    rows.sort(key=lambda row: (row["rank"], KINDS.index(row["kind"]), row["name"] or "", row["department"] or ""))
    return [{key: row[key] for key in ("uid", "name", "kind", "code", "department")} for row in rows[:limit]]
