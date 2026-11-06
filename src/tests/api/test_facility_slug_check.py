"""GET /facility-slugs: the slug a facility would get, or whether a chosen one is free.

The creation and edit forms show the generated slug and let people change it;
the form may only be confirmed with a free slug, so the check answers with a
few free alternatives the person can pick instead. The save still re-checks:
this answer is a convenience, not the guarantee.

Public on purpose: a slug is a public address already.
"""
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

URL = "/facility-slugs"
PLACE = {"name": "Zzcab", "commune": "Lyon", "street": "1 rue Test"}


@pytest.fixture
async def taken(neo4j_graph):
    await neo4j_graph.cypher_query(
        "CREATE (:Facility {uid: 'zz-f1', slug: 'zzcab'}) CREATE (:Facility {uid: 'zz-f2', slug: 'zzcab-lyon'})"
    )


async def test_without_a_slug_the_most_readable_free_one_is_proposed(client, taken):
    body = (await client.get(URL, params=PLACE)).json()
    assert body["slug"] == "zzcab-rue-test-lyon"
    assert body["free"] is True and body["reason"] is None
    assert len(body["suggestions"]) == 2
    assert not {"zzcab", "zzcab-lyon", body["slug"]} & set(body["suggestions"])


async def test_a_taken_slug_is_refused_with_free_ones_to_pick(client, taken):
    body = (await client.get(URL, params={**PLACE, "slug": "zzcab"})).json()
    assert body["slug"] == "zzcab"
    assert body["free"] is False and body["reason"] == "taken"
    assert body["suggestions"][0] == "zzcab-rue-test-lyon"
    assert len(body["suggestions"]) == 3


async def test_a_free_slug_is_accepted_as_typed(client, taken):
    body = (await client.get(URL, params={**PLACE, "slug": "chez-zzcab"})).json()
    assert body["slug"] == "chez-zzcab" and body["free"] is True


async def test_a_slug_that_is_not_lowercase_words_and_hyphens_is_refused(client, taken):
    body = (await client.get(URL, params={**PLACE, "slug": "Zz Cab!"})).json()
    assert body["free"] is False and body["reason"] == "invalid"
    assert body["suggestions"]


async def test_a_facility_being_edited_may_keep_its_slug(client, taken):
    body = (await client.get(URL, params={**PLACE, "slug": "zzcab", "exclude": "zz-f1"})).json()
    assert body["free"] is True


@pytest.fixture
async def kinds(neo4j_graph):
    await neo4j_graph.cypher_query(
        "CREATE (:EffectorType {uid: 'zz-kine', name_fr: 'zzkiné', label_fr: 'zzkiné', nature: 'profession',"
        " facility_noun_fr: 'cabinet de kinésithérapie'})"
        " CREATE (:EffectorType {uid: 'zz-svc', name_fr: 'zzservice', label_fr: 'zzservice', nature: 'service'})"
        " CREATE (:Effector {uid: 'zz-urps', name_fr: 'URPS médecins libéraux'})"
    )


NO_NAME = {"commune": "Lyon", "street": "1 rue Test"}


async def test_a_nameless_office_is_named_by_its_occupation_and_street(client, kinds):
    body = (await client.get(URL, params={**NO_NAME, "effector_type": "zz-kine"})).json()
    assert body["slug"] == "cabinet-de-kinesitherapie-rue-test-lyon"
    assert "cabinet-de-kinesitherapie" not in body["suggestions"]


async def test_a_service_is_named_by_its_organisation(client, kinds):
    body = (await client.get(URL, params={**NO_NAME, "effector_type": "zz-svc", "effector": "zz-urps"})).json()
    assert body["slug"] == "urps-medecins-liberaux"


async def test_a_name_the_person_typed_beats_the_occupation(client, kinds):
    body = (await client.get(URL, params={**NO_NAME, "name": "Zzcab", "effector_type": "zz-kine"})).json()
    assert body["slug"] == "zzcab"


async def test_nothing_to_build_a_slug_from_proposes_none(client, kinds):
    body = (await client.get(URL, params={"commune": "Lyon"})).json()
    assert body["slug"] is None and body["free"] is False and body["reason"] == "invalid"
