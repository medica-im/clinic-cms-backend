"""Cloning a directory copies what decides its lists, not only its entries.

A clone of the santé mentale directory landed all 96 entries on staging and listed
all 96, porteurs included, where dev lists 73: the LISTS_NEED edge that filters the
list stayed behind on dev. The entries were identical; the directory was not.

What travels, each found here by a key every server shares:

- the needs it lists (LISTS_NEED, by Need slug) and the types it offers
  (OFFERS_EFFECTOR_TYPE, by EffectorType name_fr): they decide what the directory
  shows, so a clone applies them unless the superuser unticks them;
- whether it lists its owner's entry, and the minimum role to read it: access and
  display choices a deployment may make differently on purpose (a directory still
  reserved on production while it is built), so applied only when ticked.

Copying a set makes it equal to the source's: missing edges added, extra ones
removed. A need or type the source names that does not exist here is reported and
skipped, never created: reference data comes from the console.
"""
import pytest
import pytest_asyncio
from neomodel import adb

from api.serializers.clone import directory_settings as ds
from api.serializers.clone.token import token_reads
from api.types.clone import DirectorySnapshot

TAG = "e2eCloneDirSettings"
DIR = f"{TAG}-dir"


def snapshot(**over):
    return DirectorySnapshot(**{"lists_needs": [], "offered_types": [], "list_owner_entry": True,
                                "minimum_role": "anonymous", **over})


class TestDifferences:
    def test_identical_directories_differ_in_nothing(self):
        assert ds.differences(snapshot(lists_needs=["a"]), snapshot(lists_needs=["a"]), {}) == []

    def test_the_listed_needs_differ_and_are_applied_by_default(self):
        [d] = ds.differences(snapshot(lists_needs=["sante-mentale"]), snapshot(), {})
        assert (d.key, d.source, d.here, d.applied_by_default) == ("lists_needs", ["sante-mentale"], [], True)

    def test_the_offered_types_are_applied_by_default(self):
        [d] = ds.differences(snapshot(offered_types=["CMP"]), snapshot(), {})
        assert (d.key, d.applied_by_default) == ("offered_types", True)

    @pytest.mark.parametrize("over", [{"list_owner_entry": False}, {"minimum_role": "staff"}])
    def test_access_and_display_choices_wait_for_a_tick(self, over):
        [d] = ds.differences(snapshot(**over), snapshot(), {})
        assert d.applied_by_default is False

    def test_what_the_source_names_but_this_server_lacks_is_reported(self):
        [d] = ds.differences(snapshot(lists_needs=["a", "b"]), snapshot(), {"lists_needs": ["b"]})
        assert d.missing_here == ["b"]


class TestTheTokenReadsOneDirectory:
    def test_a_session_reads_any_directory_of_its_site(self):
        assert token_reads(None, "cpts-lyon-3-sante-mentale") is True

    def test_a_token_reads_the_directory_it_was_minted_for(self):
        claims = type("Claims", (), {"directory": "cpts-lyon-3-sante-mentale"})()
        assert token_reads(claims, "cpts-lyon-3-sante-mentale") is True
        assert token_reads(claims, "santelyon3") is False


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def graph():
    await adb.cypher_query("MATCH (n) WHERE n.uid STARTS WITH $tag DETACH DELETE n", {"tag": TAG})
    await adb.cypher_query(
        """
        CREATE (d:Directory {uid:$tag+'-dir', name:$dir})
        CREATE (:Need {uid:$tag+'-need-a', slug:$tag+'-a', name_fr:'A'})
        CREATE (:Need {uid:$tag+'-need-b', slug:$tag+'-b', name_fr:'B'})
        CREATE (:EffectorType {uid:$tag+'-type-x', name_fr:$tag+' X'})
        CREATE (:EffectorType {uid:$tag+'-type-y', name_fr:$tag+' Y'})
        """,
        {"tag": TAG, "dir": DIR},
    )
    yield
    await adb.cypher_query("MATCH (n) WHERE n.uid STARTS WITH $tag DETACH DELETE n", {"tag": TAG})


async def _set(**over):
    await ds.apply(DIR, snapshot(**over), list(over), main=False)


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
class TestReadAndApply:
    async def test_an_untouched_directory_reads_as_the_defaults(self, graph):
        await adb.cypher_query("MATCH (d:Directory {name:$d}) REMOVE d.list_owner_entry, d.minimum_role", {"d": DIR})
        assert await ds.read(DIR) == snapshot()

    async def test_the_listed_needs_become_the_sources(self, graph):
        await _set(lists_needs=[f"{TAG}-a"])
        await _set(lists_needs=[f"{TAG}-b"])
        assert (await ds.read(DIR)).lists_needs == [f"{TAG}-b"]

    async def test_the_offered_types_become_the_sources(self, graph):
        await _set(offered_types=[f"{TAG} X", f"{TAG} Y"])
        await _set(offered_types=[f"{TAG} Y"])
        assert (await ds.read(DIR)).offered_types == [f"{TAG} Y"]

    async def test_what_is_not_here_is_skipped_and_reported(self, graph):
        warnings = await ds.apply(DIR, snapshot(lists_needs=[f"{TAG}-a", f"{TAG}-nowhere"]), ["lists_needs"], main=False)
        assert (await ds.read(DIR)).lists_needs == [f"{TAG}-a"]
        assert any(f"{TAG}-nowhere" in w for w in warnings)

    async def test_the_missing_ones_are_named_before_applying(self, graph):
        missing = await ds.unknown_here(snapshot(lists_needs=[f"{TAG}-a", f"{TAG}-nowhere"],
                                                 offered_types=[f"{TAG} Z"]))
        assert missing == {"lists_needs": [f"{TAG}-nowhere"], "offered_types": [f"{TAG} Z"]}

    async def test_only_the_chosen_settings_are_applied(self, graph):
        await ds.apply(DIR, snapshot(list_owner_entry=False, minimum_role="staff"), ["list_owner_entry"], main=False)
        read = await ds.read(DIR)
        assert (read.list_owner_entry, read.minimum_role) == (False, "anonymous")

    async def test_the_minimum_role_is_applied_when_chosen(self, graph):
        await _set(minimum_role="staff")
        assert (await ds.read(DIR)).minimum_role == "staff"

    async def test_a_sites_own_directory_stays_public(self, graph):
        """Like the directories page's 409: the site's own directory is public by definition."""
        await _set(minimum_role="anonymous")
        warnings = await ds.apply(DIR, snapshot(minimum_role="staff"), ["minimum_role"], main=True)
        assert (await ds.read(DIR)).minimum_role == "anonymous"
        assert warnings
