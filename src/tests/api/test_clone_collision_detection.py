"""What cloning an entry would collide with here, before anything is written.

`assert_slug_is_free` raises 409 *during* a write, and `create_entry` answers a
duplicate (person, occupation, place) with a 452 after an effector and a
facility already exist. Neither is usable for a preview, which is the whole
point of cloning between deployments: the superuser sees what will happen first.

Two rules are asserted, and they differ on purpose.

**People resolve silently.** RPPS decides when present — it is a national
registration number, so the same number is the same practitioner — and name plus
gender decides otherwise. Neither prompts, because a prompt on every entry
trains people to click through them.

**Facilities can prompt.** A building has no national identifier, and reusing
the wrong one rewrites an address or makes a slug unreachable, so anything short
of an exact BAN match asks.
"""
import pytest
import pytest_asyncio
from neomodel import adb

from api.serializers.clone import detect

# One loop for the whole session. `adb` is a process-global connection whose
# sockets are bound to the loop that opened them, so a function-scoped async
# fixture reconnects on a second loop and every test after the first fails on
# "attached to a different loop" rather than on anything it asserts.
pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

TAG = "e2eCloneDetect"


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def graph():
    """A small, self-contained corner of the graph, torn down after."""
    # Clean first: a fixture that half-succeeded leaves nodes behind, and every
    # later run then fails on the uid constraint rather than on anything real.
    await adb.cypher_query(
        "MATCH (n) WHERE n.uid STARTS WITH $tag OR n.slug STARTS WITH $tag "
        "DETACH DELETE n", {"tag": TAG}
    )
    await adb.cypher_query(
        """
        CREATE (c:Commune {uid:$tag+'-commune', name_fr:'Testville'})
        CREATE (d:DepartmentOfFrance {uid:$tag+'-dept', name_fr:'Testdept'})
        CREATE (c)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(d)
        CREATE (org:Entry {uid:$tag+'-org', slug:$tag+'-org', active:true})
        CREATE (t:EffectorType {uid:$tag+'-type', unique_ID:$tag+'-UID',
                                name_fr:'testeur', slug_fr:$tag+'-type-slug'})
        CREATE (f:Facility {uid:$tag+'-fac', name:'Cabinet Test', slug:$tag+'-fac-slug',
                            street:'1 Rue du Test', zip:'00000', ban_id:'BAN-TEST-1'})
        CREATE (f)-[:PART_OF]->(org)
        CREATE (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (e:Effector:HealthWorker {uid:$tag+'-eff', name_fr:'Jean Test',
                                         gender:'M', rpps:99900011122})
        CREATE (plain:Effector {uid:$tag+'-eff2', name_fr:'Marie Test', gender:'F'})
        CREATE (entry:Entry {uid:$tag+'-entry', slug:$tag+'-entry-slug', active:true})
        CREATE (entry)-[:HAS_EFFECTOR]->(e)
        CREATE (entry)-[:HAS_EFFECTOR_TYPE]->(t)
        CREATE (entry)-[:HAS_FACILITY]->(f)
        """,
        {"tag": TAG},
    )
    yield f"{TAG}-org"
    await adb.cypher_query(
        "MATCH (n) WHERE n.uid STARTS WITH $tag OR n.slug STARTS WITH $tag "
        "DETACH DELETE n", {"tag": TAG}
    )


class TestReferenceData:
    async def test_effector_type_resolves_by_unique_id_first(self, graph):
        uid = await detect.resolve_effector_type(
            {"unique_ID": f"{TAG}-UID", "slug": "wrong", "name": "wrong"}
        )
        assert uid == f"{TAG}-type"

    async def test_effector_type_falls_back_to_slug_then_name(self, graph):
        assert await detect.resolve_effector_type({"slug": f"{TAG}-type-slug"}) == f"{TAG}-type"
        assert await detect.resolve_effector_type({"name": "testeur"}) == f"{TAG}-type"

    async def test_an_unknown_effector_type_resolves_to_nothing(self, graph):
        """A blocker, not an invention.

        Creating one would put a new occupation into the directory as a side
        effect of copying a person.
        """
        assert await detect.resolve_effector_type({"name": "no such occupation"}) is None


class TestPeopleResolveSilently:
    async def test_the_same_rpps_is_the_same_practitioner(self, graph):
        plan, warnings = await detect.plan_effector(
            {"name": "Spelled Differently", "gender": "M", "rpps": {"rpps": 99900011122}}
        )
        assert plan.default_resolution == "reuse"
        assert plan.local_uid == f"{TAG}-eff"
        assert plan.auto, "an RPPS match must not prompt"
        assert not warnings

    async def test_name_and_gender_decide_when_there_is_no_rpps(self, graph):
        plan, warnings = await detect.plan_effector({"name": "Marie Test", "gender": "F"})
        assert plan.default_resolution == "reuse"
        assert plan.local_uid == f"{TAG}-eff2"
        assert plan.auto, "name and gender matching must not prompt either"

    async def test_an_unknown_person_is_created(self, graph):
        plan, _ = await detect.plan_effector({"name": "Nobody Here", "gender": "F"})
        assert plan.default_resolution == "create"
        assert plan.auto

    async def test_a_namesake_with_a_different_rpps_is_a_different_person(self, graph):
        """The one case reuse would be unrecoverable.

        Two RPPS numbers are two registered practitioners. Merging them would
        join two people's records with no way back, so this creates — and says
        so, rather than asking.
        """
        plan, warnings = await detect.plan_effector(
            {"name": "Jean Test", "gender": "M", "rpps": {"rpps": 12300000000}}
        )
        assert plan.default_resolution == "create"
        assert any("different RPPS" in w for w in warnings)


class TestFacilitiesCanPrompt:
    def _incoming(self, **over):
        base = {
            "facility": {"name": "Cabinet Test", "slug": f"{TAG}-fac-slug"},
            "address": {"street": "1 Rue du Test", "zip": "00000", "city": "Testville"},
            "ban_id": "BAN-TEST-1",
        }
        for k, v in over.items():
            if k in ("facility", "address"):
                base[k] = {**base[k], **v}
            else:
                base[k] = v
        return base

    async def test_an_exact_ban_match_reuses_without_asking(self, graph):
        plan = await detect.plan_facility(self._incoming(), f"{TAG}-org")
        assert plan.default_resolution == "reuse"
        assert plan.local_uid == f"{TAG}-fac"
        assert plan.auto, "an identical building should not need confirmation"

    async def test_a_ban_match_with_differences_asks(self, graph):
        """Same building, different details: the superuser decides.

        Reusing silently would keep whichever address the local record has and
        quietly discard the source's.
        """
        plan = await detect.plan_facility(
            self._incoming(facility={"name": "Cabinet Renamed"}), f"{TAG}-org"
        )
        assert plan.default_resolution == "reuse"
        assert not plan.auto
        assert "name" in plan.matches[0].differing_fields

    async def test_an_address_match_asks(self, graph):
        plan = await detect.plan_facility(
            self._incoming(ban_id=None, facility={"name": "Other name", "slug": "other"}),
            f"{TAG}-org",
        )
        assert plan.matches and plan.matches[0].reason == "address"
        assert not plan.auto

    async def test_a_name_match_asks(self, graph):
        plan = await detect.plan_facility(
            self._incoming(ban_id=None, address={"street": "99 Elsewhere"},
                           facility={"slug": "different-slug"}),
            f"{TAG}-org",
        )
        assert plan.matches and plan.matches[0].reason == "name"
        assert not plan.auto

    async def test_a_slug_match_asks(self, graph):
        """A slug clash is what makes one of two facilities unreachable."""
        plan = await detect.plan_facility(
            self._incoming(ban_id=None, address={"street": "99 Elsewhere"},
                           facility={"name": "Totally Different"}),
            f"{TAG}-org",
        )
        assert plan.matches and plan.matches[0].reason == "slug"
        assert not plan.auto

    async def test_an_unrelated_facility_is_created(self, graph):
        plan = await detect.plan_facility(
            self._incoming(ban_id="BAN-OTHER", address={"street": "42 Nowhere"},
                           facility={"name": "Brand New", "slug": "brand-new"}),
            f"{TAG}-org",
        )
        assert plan.default_resolution == "create"
        assert plan.auto

    async def test_another_organizations_facility_is_not_a_match(self, graph):
        """Scoped like assert_slug_is_free.

        Two unrelated organizations are each entitled to a "pharmacie"; only a
        clash within one is a problem.
        """
        plan = await detect.plan_facility(self._incoming(), "some-other-org-uid")
        assert plan.default_resolution == "create"


class TestTheEntryItself:
    async def test_an_existing_triple_is_found(self, graph):
        """create_entry's 452, detected before an effector and facility exist."""
        slug = await detect.entry_already_here(
            f"{TAG}-eff", f"{TAG}-type", f"{TAG}-fac"
        )
        assert slug == f"{TAG}-entry-slug"

    async def test_a_new_triple_is_not(self, graph):
        assert await detect.entry_already_here(
            f"{TAG}-eff2", f"{TAG}-type", f"{TAG}-fac"
        ) is None


class TestWhatIsAlreadyHere:
    """Which of a source directory's entries this instance already holds.

    Decorates the picker so a superuser does not select an entry that preflight
    would only reject afterwards. Matched on the person's name and their
    occupation, because uids are per-deployment — the same practitioner is a
    different node here.

    Deliberately looser than create_entry's identity rule, which is
    (effector, effector_type, facility): this runs over a whole directory before
    any facility has been resolved, and its job is a courtesy, not a gate.
    """

    async def test_an_entry_that_exists_here_is_reported(self, graph):
        found = await detect.already_here([
            {"uid": "src-1", "name": "Jean Test",
             "effector_type": {"name": "testeur"}},
        ])
        assert found == {"src-1": f"{TAG}-entry-slug"}, (
            "an entry the directory already holds was not reported, so the "
            "picker would offer it and preflight would reject it later"
        )

    async def test_the_match_ignores_case(self, graph):
        found = await detect.already_here([
            {"uid": "src-2", "name": "JEAN TEST",
             "effector_type": {"name": "TESTEUR"}},
        ])
        assert "src-2" in found

    async def test_the_same_person_in_another_occupation_is_not_a_duplicate(self, graph):
        """A practitioner may hold several jobs, and each is its own entry.

        Reporting this as already-here would stop a superuser cloning a genuine
        second listing.
        """
        found = await detect.already_here([
            {"uid": "src-3", "name": "Jean Test",
             "effector_type": {"name": "something else entirely"}},
        ])
        assert found == {}

    async def test_an_unknown_person_is_not_reported(self, graph):
        found = await detect.already_here([
            {"uid": "src-4", "name": "Nobody Here",
             "effector_type": {"name": "testeur"}},
        ])
        assert found == {}

    async def test_an_empty_list_costs_no_query(self, graph):
        assert await detect.already_here([]) == {}
