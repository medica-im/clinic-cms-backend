"""A facility's slug is generated, readable, and held by no other facility.

The slug is the facility's address (/sites/{slug}), so it should read like the
place and never collide. A national organisation can hold hundreds of
"pharmacie" or "cabinet-infirmier", so the name alone is not enough: the
commune, then the street, then the postcode are added until a slug is free.

Free means free across every facility, not only the organisation's. That
reverses the per-organisation scope argued in test_facility_slug_is_unique.py,
whose objection (a second organisation refused an ordinary name) no longer
holds once the second simply gets "pharmacie-lyon".

People still see the generated slug and may change it; whatever they choose is
checked against the same rule.
"""
import pytest
import pytest_asyncio
from neomodel import adb

from directory.facility_slug import facility_slug_candidates, generate_facility_slugs, slug_for_new_facility


class TestCandidates:
    def test_the_name_first_then_more_of_the_address(self):
        """The street without its number reads as a place; the number only
        comes in when that is not enough, as dedupe_facility_slugs decided."""
        assert facility_slug_candidates("Cabinet infirmier", "Lyon", "19 rue Jacqueline Auriol", "69008") == [
            "cabinet-infirmier",
            "cabinet-infirmier-lyon",
            "cabinet-infirmier-rue-jacqueline-auriol-lyon",
            "cabinet-infirmier-19-rue-jacqueline-auriol-lyon",
            "cabinet-infirmier-lyon-69008",
            "cabinet-infirmier-19-rue-jacqueline-auriol-lyon-69008",
        ]

    def test_a_street_without_a_number_is_tried_once(self):
        assert facility_slug_candidates("Cabinet", "Lyon", "Place Bellecour") == [
            "cabinet", "cabinet-lyon", "cabinet-place-bellecour-lyon",
        ]

    def test_accents_and_apostrophes_read_as_the_site_already_writes_them(self):
        assert facility_slug_candidates("Pôle Santé Gare")[0] == "pole-sante-gare"
        assert facility_slug_candidates("Cabinet d'orthophonie")[0] == "cabinet-dorthophonie"

    def test_missing_parts_are_skipped_without_repeats(self):
        assert facility_slug_candidates("Cabinet", None, None, None) == ["cabinet"]
        assert facility_slug_candidates("Cabinet", "Lyon", None, None) == ["cabinet", "cabinet-lyon"]

    def test_no_name_and_no_street_no_slug(self):
        assert facility_slug_candidates("  ", "Lyon") == []

    def test_a_facility_without_a_name_is_named_by_its_street(self):
        """Plain addresses (a practitioner's own premises) have no name. The
        number stays: it is all that tells two of them on one street apart."""
        assert facility_slug_candidates("", "Lyon", "2 Rue des Arènes", "01500") == [
            "2-rue-des-arenes",
            "2-rue-des-arenes-lyon",
            "2-rue-des-arenes-lyon-01500",
        ]


TAG = "e2eFacSlug"


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def taken():
    """Two facilities of two different organisations holding the slugs a new
    "Zzcabinet" in Lyon would want first."""
    await adb.cypher_query("MATCH (f:Facility) WHERE f.uid STARTS WITH $tag DETACH DELETE f", {"tag": TAG})
    await adb.cypher_query(
        """
        CREATE (:Facility {uid:$tag+'-a', name:'Zzcabinet', slug:'zzcabinet'})
        CREATE (:Facility {uid:$tag+'-b', name:'Zzcabinet', slug:'zzcabinet-lyon'})
        """,
        {"tag": TAG},
    )
    yield
    await adb.cypher_query("MATCH (f:Facility) WHERE f.uid STARTS WITH $tag DETACH DELETE f", {"tag": TAG})


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
class TestGenerating:
    async def test_a_free_name_is_the_slug(self, taken):
        assert (await generate_facility_slugs("Zzfree place", "Lyon"))[0] == "zzfree-place"

    async def test_a_slug_any_facility_holds_is_skipped_whatever_its_organisation(self, taken):
        slugs = await generate_facility_slugs("Zzcabinet", "Lyon", "1 rue Test", "69008")
        assert slugs[0] == "zzcabinet-rue-test-lyon"
        assert "zzcabinet" not in slugs and "zzcabinet-lyon" not in slugs

    async def test_a_facility_keeps_its_own_slug(self, taken):
        slugs = await generate_facility_slugs("Zzcabinet", "Lyon", exclude_uid=f"{TAG}-a")
        assert slugs[0] == "zzcabinet"

    async def test_several_free_slugs_to_choose_from(self, taken):
        slugs = await generate_facility_slugs("Zzcabinet", "Lyon", "1 rue Test", "69008", count=3)
        assert len(slugs) == 3 and len(set(slugs)) == 3

    async def test_when_every_readable_slug_is_taken_a_short_suffix_makes_one(self, taken):
        slugs = await generate_facility_slugs("Zzcabinet", "Lyon", count=1)
        assert len(slugs) == 1
        assert slugs[0].startswith("zzcabinet-lyon-") and slugs[0] != "zzcabinet-lyon"


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
class TestForANewFacility:
    """What create_facility stores when the form sent a slug, or none."""

    @pytest_asyncio.fixture(loop_scope="session")
    async def commune(self, taken):
        await adb.cypher_query("MATCH (c:Commune {uid: $uid}) DETACH DELETE c", {"uid": f"{TAG}-commune"})
        await adb.cypher_query(
            "CREATE (:Commune {uid: $uid, name_fr: 'Zzville'})", {"uid": f"{TAG}-commune"}
        )
        yield f"{TAG}-commune"
        await adb.cypher_query("MATCH (c:Commune {uid: $uid}) DETACH DELETE c", {"uid": f"{TAG}-commune"})

    async def test_a_slug_the_person_chose_is_kept(self, commune):
        assert await slug_for_new_facility("chez-moi", "Zzcabinet", commune, "1 rue Test", "69008") == "chez-moi"

    async def test_without_one_it_is_generated_from_the_name_and_the_commune(self, commune):
        assert await slug_for_new_facility(None, "Zzcabinet", commune, "1 rue Test", "69008") == "zzcabinet-zzville"

    async def test_a_blank_slug_counts_as_none(self, commune):
        assert await slug_for_new_facility("  ", "Zzcabinet", commune, None, None) == "zzcabinet-zzville"

    async def test_an_unknown_commune_still_gives_a_slug(self, commune):
        assert await slug_for_new_facility(None, "Zzfree place", "no-such-commune", None, None) == "zzfree-place"
