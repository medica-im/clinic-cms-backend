"""Planning the repair of facility slugs already in the graph.

Production holds slugs shared by several facilities ("cabinet-infirmier" twice
on santelyon3.fr, so one of the two has no reachable page) and a facility with
no slug. The plan keeps a shared slug on the facility that matters most, the one
with the most active entries, and gives every other holder a generated slug, as
the creation form now would. Planning reads the graph and changes nothing.
"""
import pytest
import pytest_asyncio
from neomodel import adb

from directory.facility_slug import merge_facility, plan_facility_merges, plan_slug_repairs

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

TAG = "e2eRepair"
ALL = "MATCH (n) WHERE n.uid STARTS WITH $tag DETACH DELETE n"


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def graph():
    await adb.cypher_query(ALL, {"tag": TAG})
    await adb.cypher_query(
        """
        CREATE (c:Commune {uid: $tag+'-c', name_fr: 'Zzville'})
        CREATE (busy:Facility {uid: $tag+'-busy', name: 'Zzdup', slug: 'zzdup', street: '1 rue A'})
        CREATE (idle:Facility {uid: $tag+'-idle', name: 'Zzdup', slug: 'zzdup', street: '2 rue B'})
        CREATE (idle2:Facility {uid: $tag+'-idle2', name: 'Zzdup', slug: 'zzdup', street: '3 rue C'})
        CREATE (orphan:Facility {uid: $tag+'-orphan', name: 'Zzorphan'})
        CREATE (alone:Facility {uid: $tag+'-alone', name: 'Zzalone', slug: 'zzalone'})
        CREATE (busy)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (idle)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (idle2)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (orphan)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (e1:Entry {uid: $tag+'-e1', active: true})-[:HAS_FACILITY]->(busy)
        CREATE (e2:Entry {uid: $tag+'-e2', active: true})-[:HAS_FACILITY]->(busy)
        CREATE (e3:Entry {uid: $tag+'-e3', active: false})-[:HAS_FACILITY]->(idle)

        CREATE (t:EffectorType {uid: $tag+'-t', name_fr: 'zztesteur'})
        CREATE (pa:Effector {uid: $tag+'-pa', name_fr: 'Zz A'})
        CREATE (pb:Effector {uid: $tag+'-pb', name_fr: 'Zz B'})
        CREATE (pc:Effector {uid: $tag+'-pc', name_fr: 'Zz C'})
        CREATE (u:User {uid: $tag+'-user'})
        CREATE (p1:Facility {uid: $tag+'-p1', name: 'Zzpharma', slug: 'zzpharma', street: '12 Bd X', zip: '69003'})
        CREATE (p2:Facility {uid: $tag+'-p2', name: 'Zzpharma', slug: 'zzpharma', street: '12 Bd X', zip: '69003'})
        CREATE (p3:Facility {uid: $tag+'-p3', name: 'Zzpharma', slug: 'zzpharma', street: '12 Bd X', zip: '69003'})
        CREATE (p2)-[:OWNED_BY]->(u)
        CREATE (ep1:Entry {uid: $tag+'-ep1', active: true})-[:HAS_FACILITY]->(p1)
        CREATE (ep2:Entry {uid: $tag+'-ep2', active: true})-[:HAS_FACILITY]->(p2)
        CREATE (ep3:Entry {uid: $tag+'-ep3', active: true})-[:HAS_FACILITY]->(p3)
        CREATE (ep1)-[:HAS_EFFECTOR]->(pa) CREATE (ep1)-[:HAS_EFFECTOR_TYPE]->(t)
        CREATE (ep2)-[:HAS_EFFECTOR]->(pb) CREATE (ep2)-[:HAS_EFFECTOR_TYPE]->(t)
        CREATE (ep3)-[:HAS_EFFECTOR]->(pc) CREATE (ep3)-[:HAS_EFFECTOR_TYPE]->(t)

        CREATE (n1:Facility {uid: $tag+'-n1', name: '', slug: '1-rue-zznl', street: '1 rue Zznl', zip: '69001'})
        CREATE (n2:Facility {uid: $tag+'-n2', name: '', slug: '1-rue-zznl', street: '2 rue Zznl', zip: '69001'})
        CREATE (n3:Facility {uid: $tag+'-n3', street: '9 rue Zznobody', zip: '69001'})
        CREATE (en1:Entry {uid: $tag+'-en1', active: true})-[:HAS_FACILITY]->(n1)
        CREATE (en2:Entry {uid: $tag+'-en2', active: true})-[:HAS_FACILITY]->(n2)
        CREATE (en3:Entry {uid: $tag+'-en3', active: true})-[:HAS_FACILITY]->(n2)
        CREATE (q1:Facility {uid: $tag+'-q1', name: 'Zzlab', slug: 'zzlab', street: '5 rue Q', zip: '69001'})
        CREATE (q2:Facility {uid: $tag+'-q2', name: 'zzlab ', slug: 'zzlab', street: '5 Rue Q', zip: '69001'})
        CREATE (eq1:Entry {uid: $tag+'-eq1', active: true})-[:HAS_FACILITY]->(q1)
        CREATE (eq2:Entry {uid: $tag+'-eq2', active: true})-[:HAS_FACILITY]->(q2)
        CREATE (eq1)-[:HAS_EFFECTOR]->(pa) CREATE (eq1)-[:HAS_EFFECTOR_TYPE]->(t)
        CREATE (eq2)-[:HAS_EFFECTOR]->(pa) CREATE (eq2)-[:HAS_EFFECTOR_TYPE]->(t)
        """,
        {"tag": TAG},
    )
    yield
    await adb.cypher_query(ALL, {"tag": TAG})


async def attachments(uid: str) -> bool:
    """Postgres holds a facility's contacts and images; p3 has some."""
    return uid.endswith("-p3")


async def mine():
    plan = await plan_slug_repairs(has_attachments=attachments)
    return {r.uid.removeprefix(f"{TAG}-"): r for r in plan if r.uid.startswith(TAG)}


async def merges():
    plan = await plan_facility_merges(has_attachments=attachments)
    return {m.drop_uid.removeprefix(f"{TAG}-"): m for m in plan if m.drop_uid.startswith(TAG)}


async def test_the_facility_with_most_active_entries_keeps_a_shared_slug(graph):
    plan = await mine()
    assert "busy" not in plan, "the facility people reach by that slug must not move"


async def test_every_other_holder_gets_a_generated_slug(graph):
    plan = await mine()
    assert plan["idle"].reason == "shared" and plan["idle"].old == "zzdup"
    assert plan["idle2"].reason == "shared"
    assert plan["idle"].new != plan["idle2"].new, "two renames may not take the same slug"
    assert "zzdup" not in {plan["idle"].new, plan["idle2"].new}


async def test_inactive_entries_do_not_count(graph):
    """idle has an entry, but an inactive one: busy still wins and idle moves."""
    assert "idle" in await mine()


async def test_a_facility_without_a_slug_gets_one(graph):
    plan = await mine()
    assert plan["orphan"].reason == "missing" and plan["orphan"].old is None
    assert plan["orphan"].new == "zzorphan"


async def test_a_facility_alone_with_its_slug_is_left_alone(graph):
    assert "alone" not in await mine()


async def test_planning_writes_nothing(graph):
    await mine()
    rows, _ = await adb.cypher_query(
        "MATCH (f:Facility) WHERE f.uid STARTS WITH $tag RETURN f.uid, f.slug ORDER BY f.uid", {"tag": TAG}
    )
    assert dict(rows)[f"{TAG}-idle"] == "zzdup" and dict(rows)[f"{TAG}-orphan"] is None


class TestSameNameSameAddress:
    """Identical name and address under one slug is one place recorded several
    times, not several places: renaming them would keep the duplicate for good.
    They are merged into the facility with the most active entries."""

    async def test_duplicates_are_merged_into_the_facility_with_most_entries(self, graph):
        found = await merges()
        assert found["p2"].keep_uid == f"{TAG}-p1" and found["p2"].blocked is None
        assert found["p2"].entries == 1

    async def test_the_kept_facility_is_not_a_duplicate_of_itself(self, graph):
        assert "p1" not in await merges()

    async def test_names_and_streets_compare_without_case_or_stray_spaces(self, graph):
        found = await merges()
        assert found["q2"].keep_uid == f"{TAG}-q1"

    async def test_a_duplicate_with_contacts_or_images_is_left_for_a_person(self, graph):
        found = await merges()
        assert found["p3"].blocked == "has contacts or images"

    async def test_the_same_person_in_the_same_occupation_would_collide(self, graph):
        found = await merges()
        assert found["q2"].blocked == "same person and occupation already at the kept facility"

    async def test_duplicates_are_not_also_renamed(self, graph):
        plan = await mine()
        assert not {"p1", "p2", "p3", "q1", "q2"} & set(plan)

    async def test_planning_writes_nothing(self, graph):
        await merges()
        rows, _ = await adb.cypher_query("MATCH (f:Facility {uid: $uid}) RETURN count(f)", {"uid": f"{TAG}-p2"})
        assert rows[0][0] == 1


class TestMerging:
    async def test_the_entries_and_the_owners_move_and_the_duplicate_goes(self, graph):
        await merge_facility(f"{TAG}-p1", f"{TAG}-p2")
        rows, _ = await adb.cypher_query(
            "MATCH (e:Entry)-[:HAS_FACILITY]->(f:Facility {uid: $keep}) RETURN e.uid ORDER BY e.uid",
            {"keep": f"{TAG}-p1"},
        )
        assert [r[0] for r in rows] == [f"{TAG}-ep1", f"{TAG}-ep2"]
        owned, _ = await adb.cypher_query(
            "MATCH (:Facility {uid: $keep})-[:OWNED_BY]->(u:User) RETURN u.uid", {"keep": f"{TAG}-p1"}
        )
        assert [r[0] for r in owned] == [f"{TAG}-user"]
        gone, _ = await adb.cypher_query("MATCH (f:Facility {uid: $uid}) RETURN count(f)", {"uid": f"{TAG}-p2"})
        assert gone[0][0] == 0

    async def test_a_merge_that_would_collide_changes_nothing(self, graph):
        """The refusal comes before the first entry moves, so nothing is half done."""
        await adb.cypher_query(
            "MATCH (f:Facility {uid: $uid}) CREATE (:Entry {uid: $e, active: true})-[:HAS_FACILITY]->(f)",
            {"uid": f"{TAG}-q2", "e": f"{TAG}-stuck"},
        )
        with pytest.raises(ValueError, match="same person and occupation"):
            await merge_facility(f"{TAG}-q1", f"{TAG}-q2")
        rows, _ = await adb.cypher_query("MATCH (f:Facility {uid: $uid}) RETURN count(f)", {"uid": f"{TAG}-q2"})
        assert rows[0][0] == 1


class TestFacilitiesWithoutAName:
    """Plain addresses, with no name, are named by their street."""

    async def test_a_shared_slug_stays_with_the_address_it_describes(self, graph):
        """n2 has more entries, but '1-rue-zznl' describes n1's address."""
        plan = await mine()
        assert "n1" not in plan
        assert plan["n2"].reason == "shared" and plan["n2"].new == "2-rue-zznl"

    async def test_a_nameless_facility_without_a_slug_is_left_alone(self, graph):
        """It works by uid; a slug is not needed for the slugs to be unique."""
        assert "n3" not in await mine()
