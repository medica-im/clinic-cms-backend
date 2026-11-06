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

from directory.facility_slug import facility_slug_candidates, generate_facility_slugs, slug_base, slug_for_new_facility


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


class TestGenericBase:
    """A place word such as "cabinet de kinésithérapie" is what dozens of
    facilities in one commune have in common: it never stands alone, nor with
    only the commune, so the street is what makes the address."""

    def test_the_street_comes_before_anything_else(self):
        assert facility_slug_candidates(
            "cabinet de kinésithérapie", "Lyon", "19 rue Jacqueline Auriol", "69008", generic=True
        ) == [
            "cabinet-de-kinesitherapie-rue-jacqueline-auriol-lyon",
            "cabinet-de-kinesitherapie-19-rue-jacqueline-auriol-lyon",
            "cabinet-de-kinesitherapie-19-rue-jacqueline-auriol-lyon-69008",
        ]

    def test_neither_the_bare_word_nor_the_word_and_commune_is_offered(self):
        slugs = facility_slug_candidates("cabinet médical", "Lyon", "Place Bellecour", generic=True)
        assert "cabinet-medical" not in slugs and "cabinet-medical-lyon" not in slugs

    def test_without_a_street_there_is_nothing_to_tell_two_apart(self):
        assert facility_slug_candidates("cabinet médical", "Lyon", None, generic=True) == []

    def test_a_real_name_keeps_its_order(self):
        assert facility_slug_candidates("EcoGéPsy", "Lyon", "1 rue Test", generic=False)[0] == "ecogepsy"


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


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def types():
    """médecin carries "cabinet médical"; généraliste below it inherits it;
    kiné has its own; orthoptiste has none; a service is no profession."""
    await adb.cypher_query("MATCH (n) WHERE n.uid STARTS WITH $tag DETACH DELETE n", {"tag": f"{TAG}t"})
    await adb.cypher_query(
        """
        CREATE (med:EffectorType {uid:$tag+'-med', name_fr:$tag+'médecin', label_fr:$tag+'médecin',
                                  nature:'profession', facility_noun_fr:'cabinet médical'})
        CREATE (gen:EffectorType {uid:$tag+'-gen', name_fr:$tag+'généraliste', label_fr:$tag+'généraliste',
                                  nature:'profession'})-[:IS_A]->(med)
        CREATE (:EffectorType {uid:$tag+'-kine', name_fr:$tag+'kiné', label_fr:$tag+'kiné',
                               nature:'profession', facility_noun_fr:'cabinet de kinésithérapie'})
        CREATE (:EffectorType {uid:$tag+'-ortho', name_fr:$tag+'orthoptiste', label_fr:$tag+'Orthoptiste',
                               nature:'profession'})
        CREATE (:EffectorType {uid:$tag+'-svc', name_fr:$tag+'service', label_fr:$tag+'service',
                               nature:'service'})
        CREATE (:Effector {uid:$tag+'-urps', name_fr:'URPS médecins libéraux'})
        """,
        {"tag": f"{TAG}t"},
    )
    yield
    await adb.cypher_query("MATCH (n) WHERE n.uid STARTS WITH $tag DETACH DELETE n", {"tag": f"{TAG}t"})


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
class TestSlugBase:
    """What a facility is called in its address, from what is known by the time
    the entry is confirmed: the type and the person, not only the facility."""

    async def test_a_name_the_person_typed_wins(self, types):
        base = await slug_base("Cabinet des Lilas", f"{TAG}t-gen", None)
        assert (base.name, base.generic) == ("Cabinet des Lilas", False)

    async def test_a_profession_gets_its_place_word(self, types):
        base = await slug_base("", f"{TAG}t-kine", None)
        assert (base.name, base.generic) == ("cabinet de kinésithérapie", True)

    async def test_a_type_inherits_the_place_word_of_its_nearest_ancestor(self, types):
        base = await slug_base(None, f"{TAG}t-gen", None)
        assert (base.name, base.generic) == ("cabinet médical", True)

    async def test_with_no_place_word_the_types_own_label_stands_in(self, types):
        base = await slug_base(" ", f"{TAG}t-ortho", None)
        assert (base.name, base.generic) == (f"{TAG}tOrthoptiste", True)

    async def test_a_service_is_named_by_its_organisation(self, types):
        base = await slug_base("", f"{TAG}t-svc", f"{TAG}t-urps")
        assert (base.name, base.generic) == ("URPS médecins libéraux", False)

    async def test_nothing_known_leaves_the_street_to_name_it(self, types):
        base = await slug_base("", None, None)
        assert (base.name, base.generic) == ("", False)


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
class TestForANewFacility:
    """What create_facility stores when the form sent a slug, or none.

    Without one it stores none: the occupation and the person, which name the
    address best, are only known when the entry is confirmed, and that is where
    the slug is set (check_facility_slug)."""

    def test_a_slug_the_person_chose_is_kept(self):
        assert slug_for_new_facility("chez-moi") == "chez-moi"

    def test_without_one_none_is_stored(self):
        assert slug_for_new_facility(None) is None

    def test_a_blank_slug_is_none_not_an_empty_string(self):
        """"" is a value: two of them would collide under a unique constraint."""
        assert slug_for_new_facility("  ") is None
