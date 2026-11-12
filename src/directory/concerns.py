"""The conditions and situations a directory offers, and the entries each one selects.

Picking X selects the entries that manage X or a descendant of X (PART_OF), never
an ancestor: in a mental health directory everything relates to mental health, so
walking up would return everything for everything. An entry manages something
through its own MANAGES or through its type's (the type's subtypes included). Only
the directory's own, active entries count, and a node no entry reaches is not
offered, so empty chapters never show. "Voir aussi" follows MAY_LEAD_TO to the
situations a condition can lead to, when those are offered too.

Selection never follows RUN_BY, and never the Need a node IMPACTS: the Need decides
what a directory lists, not what a professional picks.
"""
from api.graph import read

OFFERED = """
    MATCH (:Directory {name: $directory})-[:HAS_ENTRY]->(e:Entry)
    WHERE coalesce(e.active, true)
    CALL {
        WITH e
        MATCH (e)-[:MANAGES]->(m) WHERE m:Condition OR m:Situation
        RETURN m
        UNION
        WITH e
        MATCH (e)-[:HAS_EFFECTOR_TYPE]->(:EffectorType)-[:IS_A*0..]->(:EffectorType)-[:MANAGES]->(m)
        WHERE m:Condition OR m:Situation
        RETURN m
    }
    MATCH (m)-[:PART_OF*0..]->(a) WHERE a:Condition OR a:Situation
    WITH a, collect(DISTINCT e.uid) AS entries
    OPTIONAL MATCH (a)-[:PART_OF]->(p) WHERE p:Condition OR p:Situation
    OPTIONAL MATCH (a)-[:MAY_LEAD_TO]->(s:Situation)
    RETURN properties(a) AS node, labels(a) AS labels, entries,
           head(collect(DISTINCT p.uid)) AS parent, collect(DISTINCT s.uid) AS leads_to
"""


def _name(node: dict, is_condition: bool, language: str) -> str:
    if language == "fr":
        return (node.get("label_fr") if is_condition else None) or node["name_fr"]
    return node.get("name_en") or node["name_fr"]


async def concerns_of_directory(directory: str, language: str = "fr") -> list[dict]:
    rows = await read(OFFERED, directory=directory)
    offered = {row["node"]["uid"] for row in rows}
    concerns = []
    for row in rows:
        node = row["node"]
        is_condition = "Condition" in row["labels"]
        concerns.append(
            {
                "uid": node["uid"],
                "slug": node.get("slug"),
                "name": _name(node, is_condition, language),
                "kind": (node.get("kind") or "condition") if is_condition else "situation",
                "parent": row["parent"],
                "synonyms": list(node.get("synonyms_fr") or []) + list(node.get("synonyms_en") or []),
                "entries": sorted(row["entries"]),
                "see_also": sorted(uid for uid in row["leads_to"] if uid in offered),
            }
        )
    return sorted(concerns, key=lambda concern: concern["name"])
