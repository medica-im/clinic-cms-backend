"""GET /api/v2/entry-credits?slug=…: who a page credits, retired members included.

A programme page lists the team that built it. People leave: their entry goes
inactive, and its own page (/fullentries/slug/…) answers 404 to the public on
purpose. Their work stays theirs, though, so the page still credits them — by
name and occupation only. This endpoint is that credit:

* **Anyone may read it**, anonymous included, for active and inactive entries
  alike, in the order the page lists its team.
* **A credit, not a profile.** Name, occupation (gendered label), whether the
  entry is active, and its slug — never phones, emails, facility or uid.
* **No avatar for a retired member, whoever asks.** An active member's avatar
  follows the same access rule as everywhere else (scrub_avatar).
* **Only the site's own directory**, and only entries whose access level the
  viewer may see — the same two gates the entry page applies.
* **The retired member's own page stays 404.** Crediting them must not reopen it.
"""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from neomodel import adb

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

DIRECTORY = "credits-test"
ELSEWHERE = "credits-elsewhere"
AVATAR = {"sm": "/media/sm.png", "lg": "/media/lg.png", "raw": "/media/raw.png", "access": "anonymous"}


@pytest.fixture
async def graph(neo4j_graph):
    """Four entries of DIRECTORY plus one of another directory.

    The full shape the entry page's lookup needs (facility → commune →
    department → country), so the "page stays 404" test reaches its real check.
    """
    await adb.cypher_query(
        """
        CREATE (country:Country {uid: randomUUID(), name_fr: 'France'})
        CREATE (dpt:DepartmentOfFrance {uid: randomUUID(), name: 'Vaucluse', code: '84', slug: 'vaucluse'})
               -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(country)
        CREATE (c:AdministrativeTerritorialEntityOfFrance:Commune {uid: randomUUID(), name_fr: 'Gadagne', slug_fr: 'gadagne'})
               -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt)
        CREATE (f:Facility {uid: replace(randomUUID(), '-', ''), slug: 'msp', name: 'MSP'})
               -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (d:Directory {name: $directory}), (x:Directory {name: $elsewhere})
        WITH f, d, x
        UNWIND [
            {slug: 'charlotte-mg-84', name: 'Charlotte Goolaerts', type: 'médecin généraliste', active: false, access: null, dir: 'd'},
            {slug: 'sara-pharma-84', name: 'Sara Mombelli', type: 'pharmacien', active: true, access: 'anonymous', dir: 'd'},
            {slug: 'manon-diet-84', name: 'Manon Deloche', type: 'diététicien', active: false, access: 'anonymous', dir: 'd'},
            {slug: 'paul-staff-84', name: 'Paul Interne', type: 'coordinateur', active: true, access: 'staff', dir: 'd'},
            {slug: 'alice-admin-84', name: 'Alice Direction', type: 'coordinateur', active: true, access: 'administrator', dir: 'd'},
            {slug: 'luc-retired-staff-84', name: 'Luc Ancien', type: 'infirmier', active: false, access: 'staff', dir: 'd'},
            {slug: 'jean-ailleurs-84', name: 'Jean Ailleurs', type: 'infirmier', active: true, access: 'anonymous', dir: 'x'}
        ] AS spec
        CREATE (e:Entry {uid: replace(randomUUID(), '-', ''), slug: spec.slug, active: spec.active})
        FOREACH (_ IN CASE WHEN spec.access IS NULL THEN [] ELSE [1] END | SET e.access = spec.access)
        CREATE (e)-[:HAS_FACILITY]->(f)
        CREATE (p:Effector {uid: replace(randomUUID(), '-', ''), name_fr: spec.name, gender: 'F'})
        CREATE (e)-[:HAS_EFFECTOR]->(p)
        CREATE (p)-[:LOCATION {uid: replace(randomUUID(), '-', '')}]->(f)
        MERGE (t:EffectorType {name_fr: spec.type})
          ON CREATE SET t.uid = randomUUID(), t.label_fr = spec.type, t.slug_fr = spec.type, t.synonyms_fr = [], t.definition_fr = ''
        CREATE (e)-[:HAS_EFFECTOR_TYPE]->(t)
        FOREACH (_ IN CASE WHEN spec.dir = 'd' THEN [1] ELSE [] END | CREATE (d)-[:HAS_ENTRY]->(e))
        FOREACH (_ IN CASE WHEN spec.dir = 'x' THEN [1] ELSE [] END | CREATE (x)-[:HAS_ENTRY]->(e))
        """,
        {"directory": DIRECTORY, "elsewhere": ELSEWHERE},
    )


@contextmanager
def viewer(role, avatar=AVATAR, label=None):
    """The request's site is DIRECTORY's, seen by `role`; avatars and labels stubbed (Postgres)."""
    directory = SimpleNamespace(name=DIRECTORY, site=None)
    with patch("api.routers.entry_credits.get_directory", AsyncMock(return_value=directory)), \
         patch("api.routers.entry_credits.get_neo4j_role", AsyncMock(return_value=role)), \
         patch("api.routers.entry_credits.async_get_avatar_url", AsyncMock(side_effect=lambda *a: dict(avatar) if avatar else None)), \
         patch("api.routers.entry_credits.async_flex_effector_type_label", AsyncMock(return_value=label)):
        yield


async def credits(client, *slugs):
    response = await client.get("/api/v2/entry-credits", params=[("slug", s) for s in slugs])
    assert response.status_code == 200, response.text
    return response.json()


async def test_a_retired_member_is_credited_by_name_and_occupation(graph, versioned_client):
    with viewer(None):
        [credit] = await credits(versioned_client, "charlotte-mg-84")

    assert credit == {
        "entrySlug": "charlotte-mg-84",
        "name": "Charlotte Goolaerts",
        "effector_type": {"name": "médecin généraliste", "label": "médecin généraliste"},
        "active": False,
        "avatar": None,
    }


@pytest.mark.parametrize("role", [None, "staff", "administrator", "superuser"])
async def test_a_retired_member_has_no_avatar_whoever_asks(graph, versioned_client, role):
    with viewer(role):
        [credit] = await credits(versioned_client, "manon-diet-84")

    assert credit["avatar"] is None


async def test_an_active_member_keeps_their_avatar(graph, versioned_client):
    with viewer(None):
        [credit] = await credits(versioned_client, "sara-pharma-84")

    assert credit["active"] is True
    assert credit["avatar"]["sm"] == "/media/sm.png"


async def test_an_avatar_above_the_viewers_level_is_scrubbed(graph, versioned_client):
    with viewer(None, avatar={**AVATAR, "access": "staff"}):
        [credit] = await credits(versioned_client, "sara-pharma-84")

    assert credit["avatar"] is None


async def test_credits_come_in_the_order_the_page_lists_them(graph, versioned_client):
    with viewer(None):
        listed = await credits(versioned_client, "manon-diet-84", "sara-pharma-84", "charlotte-mg-84")

    assert [c["entrySlug"] for c in listed] == ["manon-diet-84", "sara-pharma-84", "charlotte-mg-84"]


async def test_an_unknown_slug_and_another_directorys_entry_are_left_out(graph, versioned_client):
    with viewer(None):
        listed = await credits(versioned_client, "nobody-84", "jean-ailleurs-84", "sara-pharma-84")

    assert [c["entrySlug"] for c in listed] == ["sara-pharma-84"]


async def test_an_entry_restricted_to_staff_is_credited_to_staff_only(graph, versioned_client):
    with viewer(None):
        assert await credits(versioned_client, "paul-staff-84") == []
    with viewer("staff"):
        assert [c["entrySlug"] for c in await credits(versioned_client, "paul-staff-84")] == ["paul-staff-84"]


@pytest.mark.parametrize("slug, credited_to", [
    ("alice-admin-84", {"administrator", "superuser"}),
    ("luc-retired-staff-84", {"staff", "administrator", "superuser"}),
])
async def test_the_access_level_the_owner_chose_decides_who_sees_the_credit(graph, versioned_client, slug, credited_to):
    for role in (None, "staff", "administrator", "superuser"):
        with viewer(role):
            listed = [c["entrySlug"] for c in await credits(versioned_client, slug)]
        assert listed == ([slug] if role in credited_to else []), role


async def test_the_label_is_the_gendered_one(graph, versioned_client):
    with viewer(None, label="médecin généraliste (F)"):
        [credit] = await credits(versioned_client, "charlotte-mg-84")

    assert credit["effector_type"]["label"] == "médecin généraliste (F)"


async def test_a_credit_is_not_a_profile(graph, versioned_client):
    with viewer("administrator"):
        [credit] = await credits(versioned_client, "sara-pharma-84")

    assert set(credit) == {"entrySlug", "name", "effector_type", "active", "avatar"}


async def test_too_many_slugs_are_refused(graph, versioned_client):
    with viewer(None):
        response = await versioned_client.get(
            "/api/v2/entry-credits", params=[("slug", f"s{i}") for i in range(51)]
        )

    assert response.status_code == 422


async def test_the_retired_members_own_page_stays_not_found(graph, versioned_client):
    directory = SimpleNamespace(name=DIRECTORY, site=None)
    with patch("api.serializers.fullentry.get_directory", AsyncMock(return_value=directory)), \
         patch("api.serializers.fullentry.get_neo4j_role", AsyncMock(return_value=None)):
        response = await versioned_client.get("/api/v2/fullentries/slug/charlotte-mg-84")

    assert response.status_code == 404
