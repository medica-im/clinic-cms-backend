"""Cloning an entry writes it here, or leaves the graph as it was found.

The write order exists to make failure recoverable: everything cheap happens
first, each created node is recorded, and a failure before the Entry exists
takes them back. After the Entry exists nothing rolls back — that is the
staged-commit boundary, and it is deliberate. The entry is what the superuser
asked for; contacts and images are enrichment they can retry.

These tests drive `clone_one` directly against a real graph rather than through
HTTP, because what needs proving is what lands in Neo4j.
"""
import pytest
import pytest_asyncio
from neomodel import adb

from api.serializers.clone import execute
from api.types.clone import Resolution

# One loop for the session: `adb` binds its sockets to the loop that opened them.
pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

TAG = "e2eCloneExec"


#: Bumped per clone so each one is a different person.
#
# generate_entry_slugs builds candidates from the name, the occupation and the
# place, then keeps only the ones no entry holds. Cloning the *same* person to
# the same address repeatedly exhausts that list within a session and the clone
# fails on a missing slug — a fixture artefact, not the behaviour under test.
_PERSON = 0


def full_entry(**over):
    """A FullEntry-shaped payload, as the source instance would return it."""
    global _PERSON
    _PERSON += 1
    base = {
        "uid": "source-entry-uid",
        "name": f"Claude Testeur{_PERSON}",
        "label": f"Claude Testeur{_PERSON}",
        "slug": f"claude-testeur{_PERSON}",
        "gender": "M",
        "access": "anonymous",
        "carte_vitale": True,
        "effector_type": {"unique_ID": f"{TAG}-UID", "name": "testeur",
                          "slug": f"{TAG}-type-slug", "label": "testeur"},
        "facility": {"name": "Cabinet Cloné", "slug": f"{TAG}-new-fac", "label": ""},
        "address": {"street": "3 Rue Neuve", "zip": "00000", "city": "Clonetown",
                    "building": "", "geographical_complement": "",
                    "longitude": "4.85", "latitude": "45.75", "zoom": 18},
        "payment_methods": [], "third_party_payers": [], "convention": None,
        "memberships": [], "organizations": ["retired-org-node-uid"],
        "rpps": None, "spoken_languages": [],
    }
    base.update(over)
    return base


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def graph():
    await adb.cypher_query(
        "MATCH (n) WHERE n.uid STARTS WITH $tag OR n.slug STARTS WITH $tag "
        "DETACH DELETE n", {"tag": TAG})
    await adb.cypher_query(
        """
        // slug_fr and the department's name/slug are not decoration: neomodel
        // resolves these nodes when the slug generator walks the geography, and
        // a node missing a declared property does not resolve at all.
        // Both labels: Commune subclasses AdministrativeTerritorialEntityOfFrance,
        // and neomodel resolves a node by its full label set. One label short and
        // `facility.commune.all()` raises "does not resolve to any of the known
        // objects" from inside the slug generator.
        CREATE (c:Commune:AdministrativeTerritorialEntityOfFrance {uid:$tag+'-commune', name_fr:'Clonetown', slug_fr:'clonetown',
                           name_en:'Clonetown', slug_en:'clonetown',
                           wikidata:$tag+'-Q1'})
        CREATE (dep:DepartmentOfFrance {uid:$tag+'-dept', name:'Clonedept',
                                        slug:'clonedept', code:'00'})
        CREATE (c)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dep)
        CREATE (org:Entry {uid:$tag+'-org', slug:$tag+'-org', active:true})
        CREATE (d:Directory {uid:$tag+'-dir', name:$tag+'-dir'})
        CREATE (t:EffectorType {uid:$tag+'-type', unique_ID:$tag+'-UID',
                                name_fr:'testeur', slug_fr:$tag+'-type-slug'})
        """,
        {"tag": TAG},
    )
    yield {"org": f"{TAG}-org", "dir": f"{TAG}-dir"}
    # Everything the clone *created*, as well as everything the fixture did.
    #
    # A cloned entry gets a generated uid and a generated slug, so neither
    # carries the tag — matching on the prefix alone left them behind, and
    # test_entry_graph_model then failed on active entries belonging to no
    # directory. The directory edge is what identifies them: they were attached
    # to this fixture's directory, and nothing else was.
    await adb.cypher_query(
        "MATCH (d:Directory {name:$dir})-[:HAS_ENTRY]->(e:Entry) "
        "OPTIONAL MATCH (e)-[:HAS_EFFECTOR]->(eff:Effector) "
        "OPTIONAL MATCH (e)-[:HAS_FACILITY]->(f:Facility) "
        "DETACH DELETE e, eff, f", {"dir": f"{TAG}-dir"})
    await adb.cypher_query(
        "MATCH (n) WHERE n.uid STARTS WITH $tag OR n.slug STARTS WITH $tag "
        "OR n.creator_directory = $tag+'-dir' DETACH DELETE n", {"tag": TAG})


async def _clone(full, graph, **over):
    res = Resolution(source_uid=full["uid"], effector="create", facility="create", **over)
    return await execute.clone_one(
        full, res, directory_name=graph["dir"], org_uid=graph["org"],
        source_org_entry=None, creator_uid=None,
    )


class TestAHappyClone:
    async def test_it_creates_the_entry_and_attaches_it(self, graph):
        r = await _clone(full_entry(), graph)
        assert r.status == "created", r.error
        rows, _ = await adb.cypher_query(
            """
            MATCH (d:Directory {name:$dir})-[:HAS_ENTRY]->(e:Entry {uid:$uid})
            MATCH (e)-[:HAS_EFFECTOR]->(eff:Effector)
            MATCH (e)-[:HAS_EFFECTOR_TYPE]->(t:EffectorType)
            MATCH (e)-[:HAS_FACILITY]->(f:Facility)
            RETURN eff.name_fr, t.uid, f.name, e.active, e.access
            """,
            {"dir": graph["dir"], "uid": r.entry_uid},
        )
        assert rows, "the cloned entry is not attached to the target directory"
        name, type_uid, fac_name, active, access = rows[0]
        assert name.startswith("Claude Testeur")
        assert (type_uid, fac_name) == (f"{TAG}-type", "Cabinet Cloné")
        assert active is True and access == "anonymous"

    async def test_the_slug_is_regenerated_never_copied(self, graph):
        """Entry.slug is globally unique.

        Copying the source's would either violate the constraint or, worse,
        make the clone answer for the original at /e/{slug}.
        """
        source = full_entry(uid="second-source")
        r = await _clone(source, graph)
        assert r.status == "created", r.error
        assert r.entry_slug and r.entry_slug != source["slug"]

    async def test_the_facility_sits_in_exactly_one_commune(self, graph):
        """Facility.commune is cardinality One.

        Two edges make the entries query emit every entry at that facility
        twice, which doubles every count a page renders and blanks the team
        carousel. See tests/test_facility_graph_model.py.
        """
        r = await _clone(full_entry(uid="third-source"), graph)
        rows, _ = await adb.cypher_query(
            "MATCH (f:Facility {uid:$uid})-[rel:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->() "
            "RETURN count(rel)", {"uid": r.facility_uid})
        assert rows[0][0] == 1


class TestRetiredOrganizationNodes:
    async def test_edges_to_them_are_left_out(self, graph):
        """An organization is an Entry now; the Organization node is retired.

        The payload still carries an `organizations` list, and carrying it over
        would spread a shape the app no longer produces.
        """
        r = await _clone(full_entry(uid="org-edge-source"), graph)
        assert r.status == "created", r.error
        rows, _ = await adb.cypher_query(
            "MATCH (e:Entry {uid:$uid})-[:MEMBER_OF]->(o:Organization) RETURN count(o)",
            {"uid": r.entry_uid})
        assert rows[0][0] == 0, "a clone recreated an edge to a retired Organization node"


class TestWhenItCannot:
    async def test_an_unknown_effector_type_fails_before_writing(self, graph):
        before = await _count_facilities()
        r = await _clone(full_entry(uid="bad-type",
                                    effector_type={"name": "no such occupation"}), graph)
        assert r.status == "failed"
        assert "effector type" in (r.error or "")
        assert await _count_facilities() == before, "a blocked clone still wrote a facility"

    async def test_an_unknown_commune_fails_before_writing(self, graph):
        before = await _count_facilities()
        r = await _clone(full_entry(uid="bad-commune",
                                    address={"street": "x", "zip": "1", "city": "Nowhere"}),
                         graph)
        assert r.status == "failed"
        assert "commune" in (r.error or "")
        assert await _count_facilities() == before

    async def test_a_duplicate_triple_is_refused_and_compensated(self, graph):
        """create_entry's 452, caught before the entry exists.

        The facility and effector created on the way to discovering it must be
        taken back, or every rejected clone would leave two orphans behind.
        """
        first = await _clone(full_entry(uid="dup-1"), graph)
        assert first.status == "created", first.error

        before = await _count_facilities()
        second = await execute.clone_one(
            full_entry(uid="dup-2"),
            Resolution(source_uid="dup-2", effector="reuse",
                       effector_local_uid=first.effector_uid,
                       facility="reuse", facility_local_uid=first.facility_uid),
            directory_name=graph["dir"], org_uid=graph["org"],
            source_org_entry=None, creator_uid=None,
        )
        assert second.status == "failed"
        assert "already exists" in (second.error or "")
        assert await _count_facilities() == before


async def _count_facilities() -> int:
    rows, _ = await adb.cypher_query(
        "MATCH (f:Facility) WHERE f.slug STARTS WITH $tag RETURN count(f)", {"tag": TAG})
    return rows[0][0]
