"""Seeding the place words (EffectorType.facility_noun_fr) on existing types.

Types are keyed by name_fr, not uid: a uid is unique per Neo4j server only. The
seed fills the gaps and never overwrites a word someone already chose, since the
console is where those words are meant to be maintained.
"""
import pytest
import pytest_asyncio
from neomodel import adb

from directory.facility_nouns import apply_facility_nouns, plan_facility_nouns

TAG = "e2eFacNoun"

NOUNS = {
    f"{TAG} kiné": "cabinet de kinésithérapie",
    f"{TAG} sage": "cabinet de sage-femme",
    f"{TAG} dentiste": "cabinet dentaire",
    f"{TAG} absent": "cabinet fantôme",
}


@pytest_asyncio.fixture(loop_scope="session")
async def types():
    await adb.cypher_query("MATCH (n) WHERE n.uid STARTS WITH $tag DETACH DELETE n", {"tag": TAG})
    await adb.cypher_query(
        """
        CREATE (:EffectorType {uid:$tag+'-kine', name_fr:$tag+' kiné', nature:'profession'})
        CREATE (:EffectorType {uid:$tag+'-sage', name_fr:$tag+' sage', nature:'profession',
                               facility_noun_fr:'cabinet de sage-femme'})
        CREATE (:EffectorType {uid:$tag+'-dentiste', name_fr:$tag+' dentiste', nature:'profession',
                               facility_noun_fr:'cabinet de chirurgie dentaire'})
        """,
        {"tag": TAG},
    )
    yield
    await adb.cypher_query("MATCH (n) WHERE n.uid STARTS WITH $tag DETACH DELETE n", {"tag": TAG})


async def stored(uid: str):
    rows, _ = await adb.cypher_query("MATCH (t:EffectorType {uid: $uid}) RETURN t.facility_noun_fr", {"uid": uid})
    return rows[0][0]


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
class TestPlanFacilityNouns:
    async def test_a_type_without_a_word_is_given_one(self, types):
        plan = await plan_facility_nouns(NOUNS)
        assert [(c.name_fr, c.new) for c in plan.changes] == [(f"{TAG} kiné", "cabinet de kinésithérapie")]

    async def test_a_type_that_has_the_word_is_left_alone(self, types):
        plan = await plan_facility_nouns(NOUNS)
        assert f"{TAG} sage" not in [c.name_fr for c in plan.changes]
        assert f"{TAG} sage" not in [k.name_fr for k in plan.kept]

    async def test_a_word_somebody_chose_is_kept_and_reported(self, types):
        plan = await plan_facility_nouns(NOUNS)
        assert [(k.name_fr, k.old, k.new) for k in plan.kept] == [
            (f"{TAG} dentiste", "cabinet de chirurgie dentaire", "cabinet dentaire")
        ]

    async def test_a_type_missing_from_the_graph_is_reported(self, types):
        plan = await plan_facility_nouns(NOUNS)
        assert plan.missing == [f"{TAG} absent"]


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
class TestApplyFacilityNouns:
    async def test_the_planned_words_are_written_and_nothing_else(self, types):
        plan = await plan_facility_nouns(NOUNS)
        await apply_facility_nouns(plan)
        assert await stored(f"{TAG}-kine") == "cabinet de kinésithérapie"
        assert await stored(f"{TAG}-dentiste") == "cabinet de chirurgie dentaire"
        assert (await plan_facility_nouns(NOUNS)).changes == []
