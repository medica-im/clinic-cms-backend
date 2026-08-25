"""The Facility graph model — where an entry's address comes from.

A facility is a building. It stands in **exactly one** commune, has one address
and one point on the map. See ``directory/models/graph.py``, which is the
contract, and its async twin in ``agraph.py``.

This is the sibling of ``test_entry_graph_model.py``: same reasoning, the other
end of the join. That file guards the edges *out of* an Entry; this one guards
the edge out of the Facility the Entry points at.

Why this is a test and not a constraint
---------------------------------------
Neo4j 4.4 rejects relationship constraints outright::

    CREATE CONSTRAINT … FOR ()-[r:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]-() REQUIRE …
    → Neo.DatabaseError.Schema.ConstraintCreationFailed

and ``cardinality=One`` on the neomodel model is only enforced when the write
goes *through* neomodel. A raw ``MERGE`` — which this project prefers, see
CLAUDE.md — bypasses it entirely, so a second edge is accepted silently.

The damage appears far from the cause. ``get_entries_query`` in
``directory/utils.py`` joins the facility to its commune, so a facility with two
communes emits **every entry at it twice**. That doubles every count a page
renders, and it kills the team carousel: it keys its slides on ``uid``, and
duplicate keys make svelte-light-carousel render no slides at all — a blank
carousel, no error, on a page whose data looked correct in the API.

That is exactly how it was found: twelve avatar scenarios and four carousel
scenarios failing, traced clause by clause through the entries query, to twenty
worker-site facilities each carrying two commune edges. The seeder had `MERGE`d
a new one without removing the old, and nothing anywhere refused it — neither
the model, which did not declare the cardinality until this was written, nor
Neo4j, which cannot express it.

Both violations of this kind seen so far came from **seeding** code rather than
from the app, which is the same finding ``test_entry_graph_model.py`` records —
and the reason the invariant belongs in a test that names it rather than in a
comment somewhere near the write.

Scope
-----
Facilities reachable from an **active** entry. A facility nothing lists is not
rendered anywhere, and the dev dataset has accumulated orphans through years of
manual editing; asserting on those would make this permanently red instead of a
guard against new breakage.

Run
---
    pytest tests/test_facility_graph_model.py          # needs a live Neo4j
    pytest -m "not integration"                        # skips it
"""
import pytest
from neomodel import db

pytestmark = pytest.mark.integration


def _facilities_with_several_communes() -> list[tuple[str, str, int, list[str]]]:
    """Listed facilities carrying more than one commune edge.

    The facility is narrowed to the listed ones *first*, and only then are its
    commune edges counted. Written the other way round — matching entries and
    edges in one pattern — Cypher yields the cross product, so a facility with
    one commune and nine entries reports nine edges. The first version of this
    test did exactly that and accused seventy healthy facilities of holding 383
    surplus edges; every one of them had a single commune and several tenants.
    """
    rows, _ = db.cypher_query(
        """
        MATCH (entry:Entry {active: true})-[:HAS_FACILITY]->(f:Facility)
        WITH DISTINCT f
        MATCH (f)-[r:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)
        WITH f, count(r) AS edges, collect(DISTINCT c.name_fr) AS communes
        WHERE edges > 1
        RETURN f.uid, f.name, edges, communes
        ORDER BY f.name
        """
    )
    return [(uid, name, edges, communes) for uid, name, edges, communes in rows]


def test_facility_is_located_in_one_commune():
    """A building stands in one place.

    Reported with the commune names rather than a bare count, because the fix
    depends on which one is wrong: two *different* communes is a write that
    should have replaced an edge and added one instead, while two edges to the
    same commune is a MERGE that failed to match an existing relationship.
    """
    offenders = _facilities_with_several_communes()
    assert not offenders, "\n".join(
        f"{name or uid} has {edges} commune edges: {', '.join(communes)}"
        for uid, name, edges, communes in offenders
    )


def test_listed_facility_has_a_commune():
    """The other half of "exactly one": none is as broken as two.

    ``get_entries_query`` reaches the department and the country *through* the
    commune, so a facility without one drops out of the entries payload
    entirely — the entry exists, and no page lists it.
    """
    rows, _ = db.cypher_query(
        """
        MATCH (entry:Entry {active: true})-[:HAS_FACILITY]->(f:Facility)
        WHERE NOT (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(:Commune)
        RETURN DISTINCT f.uid, f.name ORDER BY f.name
        """
    )
    assert not rows, "\n".join(
        f"{name or uid} is listed by an active entry but sits in no commune"
        for uid, name in rows
    )


def test_the_entries_query_yields_one_row_per_entry():
    """The consequence, asserted directly.

    The two tests above name the cause; this one names what the reader sees. It
    walks the same joins ``get_entries_query`` does and counts the rows each
    active entry produces, so a *new* multi-valued relationship somewhere else
    on that path fails here too — even one nobody has thought to guard yet.
    """
    rows, _ = db.cypher_query(
        """
        MATCH (d:Directory)-[:HAS_ENTRY]->(entry:Entry) WHERE entry.active = true
        OPTIONAL MATCH (entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType)
        OPTIONAL MATCH (entry)-[:HAS_EFFECTOR]->(e:Effector)
        OPTIONAL MATCH (entry)-[:HAS_FACILITY]->(f:Facility)
        OPTIONAL MATCH (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)
        WITH d.name AS directory, entry.slug AS slug, count(*) AS rows
        WHERE rows > 1
        RETURN directory, slug, rows ORDER BY directory, slug
        """
    )
    assert not rows, "\n".join(
        f"{directory}: {slug} appears {n} times in the entries payload"
        for directory, slug, n in rows
    )
