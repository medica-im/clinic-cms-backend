"""The Entry graph model — the building block of the whole directory.

An Entry is the join that states "this person, in this occupation, at this
place, listed in this directory". It therefore has **exactly one** Effector,
**one** EffectorType and **one** Facility, and belongs to a Directory. Change
any one of the three and it is a different Entry. See
``directory/models/graph.py``, which is the contract.

The cardinality runs **one way only**, and the tests below assert both
directions:

* an Entry → exactly one Effector, one EffectorType, one Facility
* an Effector → **as many Entries as that person has jobs**

A physical person may hold different jobs in different facilities *or in the
same facility* — coordinator and nurse at one practice is an everyday
arrangement. So the identifying tuple is (person, occupation, place); neither
(person) nor (person, place) identifies an Entry. Anything that deduplicates
entries by person, or by person-and-facility, silently deletes a real job.

Why this is a test and not a constraint
---------------------------------------
Nothing enforces it. The only uniqueness constraints in the graph are on ``uid``
(Entry, Effector, EffectorType) and on EffectorType's name/label/slug fields,
and Neo4j 4.4 rejects relationship constraints outright::

    CREATE CONSTRAINT … FOR ()-[r:HAS_EFFECTOR_TYPE]-() REQUIRE …
    → Neo.DatabaseError.Schema.ConstraintCreationFailed

So a second HAS_EFFECTOR_TYPE edge is accepted silently, and the damage appears
far from the cause: the entries serializer emits **one row per effector type**,
so a doubly-typed entry appears twice in ``/api/v2/entries``. That doubles every
count a page renders and kills the team carousel with Svelte's
``each_key_duplicate`` (it keys slides on uid).

Both violations seen so far came from *seeding* code, not from the app: a clone
that matched the multi-valued MEMBER_OF before creating its Effector, so the
CREATE ran once per membership row and gave it three; and a seeder whose MERGE
added a second type edge rather than replacing the first. Neither failed
anywhere near where it was written, which is exactly why this belongs in a test
that names the invariant.

Scope
-----
``active`` entries only. Deactivated ones are historical records that no listing
renders, and the dev dataset has accumulated them through years of manual
editing — asserting on those would make this permanently red instead of a guard
against new breakage.

Run
---
    pytest tests/test_entry_graph_model.py            # needs a live Neo4j
    pytest -m "not integration"                        # skips it
"""
import pytest
from neomodel import db

pytestmark = pytest.mark.integration

# Relationships an Entry has exactly one of, and what each one means.
#
# MEMBER_OF is deliberately absent: it is legitimately multi-valued and points
# at two kinds of node (Organization nodes, and the organization's own Entry),
# so a real entry commonly carries three of them.
SINGLE_VALUED = {
    "HAS_EFFECTOR": "the person the entry describes",
    "HAS_EFFECTOR_TYPE": "the occupation the person is listed under",
    "HAS_FACILITY": "the place the person works at",
}


def _offenders(relationship: str) -> list[tuple[str, int]]:
    """Active entries carrying more than one edge of this kind."""
    rows, _ = db.cypher_query(
        f"""
        MATCH (e:Entry {{active: true}})-[r:{relationship}]->()
        WITH e, count(r) AS n WHERE n > 1
        RETURN e.slug, n ORDER BY n DESC, e.slug LIMIT 20
        """
    )
    return [(slug, n) for slug, n in rows]


@pytest.mark.parametrize(
    "relationship,meaning", sorted(SINGLE_VALUED.items())
)
def test_entry_has_at_most_one(relationship, meaning):
    offenders = _offenders(relationship)
    assert not offenders, (
        f"An Entry has exactly one {relationship} — {meaning}. "
        f"These carry several, so each is emitted once per edge by the "
        f"serializers and appears repeatedly in /api/v2/entries:\n  "
        + "\n  ".join(f"{slug} has {n}" for slug, n in offenders)
    )


def test_active_entry_belongs_to_a_directory():
    """An entry in no directory is unreachable by every listing."""
    rows, _ = db.cypher_query(
        """
        MATCH (e:Entry {active: true})
        WHERE NOT (:Directory)-[:HAS_ENTRY]->(e)
        RETURN e.slug ORDER BY e.slug LIMIT 20
        """
    )
    orphans = [r[0] for r in rows]
    assert not orphans, (
        "Every Entry is reached through (Directory)-[:HAS_ENTRY]->(Entry). "
        "These belong to no directory, so nothing can ever display them:\n  "
        + "\n  ".join(str(slug) for slug in orphans)
    )


def test_one_person_may_hold_several_entries():
    """A person is one Effector; each job they hold is a separate Entry.

    The cardinality is one-way — an Entry points at exactly one Effector, but an
    Effector is pointed at by as many Entries as that person has jobs. Asserting
    the reverse ("an Effector belongs to one Entry") fails against real data,
    and this test exists to stop that assertion being added: it states the
    permission, so a future reader sees shared Effectors are correct rather than
    duplication to be cleaned up.

    Real example: adeline-feldis is an IDE in 62, an IPA in 84, an IPA in 01 and
    an IDE in 69 — four Entries, one Effector.
    """
    rows, _ = db.cypher_query(
        """
        MATCH (e:Entry {active: true})-[:HAS_EFFECTOR]->(ef:Effector)
        WITH ef, count(DISTINCT e) AS entries WHERE entries > 1
        RETURN count(ef)
        """
    )
    assert rows[0][0] > 0, (
        "No Effector is shared by several Entries. Either the dataset lost its "
        "multi-job people, or something started copying the Effector per Entry "
        "— which would mean renaming a person no longer renames all their jobs."
    )


# The three ways one person legitimately holds several entries. Each is real in
# the dev dataset, and each would be destroyed by a different wrong assumption
# about what identifies an Entry.
MULTI_ENTRY_SHAPES = {
    "same facility, different occupation": (
        "size(types) > 1 AND size(facilities) = 1",
        "coordinator and nurse at one practice; pharmacien and diététicien at "
        "one pharmacy. Broken by deduplicating on (person, facility).",
    ),
    "different facility, different occupation": (
        "size(types) > 1 AND size(facilities) > 1",
        "an IDE in one department, an IPA in another. Broken by treating a "
        "person as having a single occupation.",
    ),
    "different facility, same occupation": (
        "size(types) = 1 AND size(facilities) > 1",
        "the same nurse practising at two sites. Broken by deduplicating on "
        "(person, occupation).",
    ),
}


@pytest.mark.parametrize(
    "shape,condition,rationale",
    [(name, cond, why) for name, (cond, why) in sorted(MULTI_ENTRY_SHAPES.items())],
)
def test_one_person_may_hold_several_entries_of_each_shape(shape, condition, rationale):
    """A person's identity is the Effector; each job they hold is its own Entry.

    Only the full tuple (person, occupation, place) identifies an Entry. Neither
    (person), nor (person, place), nor (person, occupation) does — so all three
    shapes below are legitimate and must keep existing.

    These are positive assertions on purpose: they state a *permission*, so that
    shared Effectors read as correct rather than as duplication someone should
    tidy up. Losing one of these counts is the signature of exactly that tidying.
    """
    rows, _ = db.cypher_query(
        f"""
        MATCH (e:Entry {{active: true}})-[:HAS_EFFECTOR]->(ef:Effector)
        MATCH (e)-[:HAS_FACILITY]->(f:Facility)
        MATCH (e)-[:HAS_EFFECTOR_TYPE]->(t:EffectorType)
        WITH ef,
             collect(DISTINCT f.uid) AS facilities,
             collect(DISTINCT t.uid) AS types,
             count(DISTINCT e) AS entries
        WHERE entries > 1 AND {condition}
        RETURN ef.name_fr ORDER BY ef.name_fr LIMIT 5
        """
    )
    assert rows, (
        f"No person in the dataset has entries of the shape '{shape}'. "
        f"That arrangement is legitimate — {rationale} "
        f"Its disappearance means either the dataset lost those people or "
        f"something is merging entries that describe different jobs."
    )
