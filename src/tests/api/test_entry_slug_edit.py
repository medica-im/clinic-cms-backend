"""Changing an entry's slug: who may, which slugs are free, and the redirect it leaves.

The owner of an entry, administrators and superusers may rename an unreadable slug.
The old slug has been shared, so it is kept (directory.EntrySlug) and redirects to the
entry. A slug another entry holds, or held, is never given away: its links would lead
to the wrong entry. An entry may take back one of its own former slugs.
Real Neo4j and Postgres: the rule spans both stores.
"""
import pytest

from directory.entry_slug import (
    EntrySlugRefused,
    change_entry_slug,
    check_entry_slug,
    slug_edit_allowed,
    slug_problem,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def graph(neo4j_graph, transactional_db):
    await neo4j_graph.cypher_query(
        """
        CREATE (d69:DepartmentOfFrance {uid: 'd-69', code: '69'})
        CREATE (lyon:Commune:AdministrativeTerritorialEntityOfFrance {uid: 'c-lyon', name_fr: 'Lyon', slug_fr: 'lyon'})
        CREATE (lyon)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(d69)
        CREATE (f:Facility {uid: 'f', zip: '69007', street: '17 Rue Crépet'})-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(lyon)
        CREATE (t:EffectorType {uid: 't', name_fr: 'association', slug_fr: 'association'})
        CREATE (mas:Entry {uid: 'mas', slug: 'le-mas-gem-69', active: true})
        CREATE (mas)-[:HAS_EFFECTOR]->(:Effector {uid: 'x', name_fr: 'Le MAS', slug_fr: 'le-mas'}),
               (mas)-[:HAS_FACILITY]->(f), (mas)-[:HAS_EFFECTOR_TYPE]->(t)
        CREATE (:Entry {uid: 'other', slug: 'unafam-association-69', active: true})
        """
    )
    return neo4j_graph


async def slug_of(graph, uid):
    rows, _ = await graph.cypher_query("MATCH (e:Entry {uid: $u}) RETURN e.slug", {"u": uid})
    return rows[0][0]


async def former(slug):
    from directory.models import EntrySlug

    row = await EntrySlug.objects.filter(slug=slug).afirst()
    return (row.entry_uid, row.replaced_by) if row else None


async def give_former(slug, entry_uid):
    from directory.models import EntrySlug

    await EntrySlug.objects.acreate(slug=slug, entry_uid=entry_uid, replaced_by="")


# --- the rule ------------------------------------------------------------------------


@pytest.mark.parametrize("slug", ["", "Le-Mas", "le mas", "le-mas-", "-le-mas", "le--mas", "lé-mas", "a" * 256])
def test_a_slug_is_lowercase_words_without_accents_joined_by_single_hyphens(slug):
    assert slug_problem(slug) == "invalid"


def test_a_well_formed_slug_has_no_problem():
    assert slug_problem("le-mas-association-69") is None


@pytest.mark.parametrize(
    "role,owner,allowed",
    [
        ("superuser", False, True),
        ("administrator", False, True),
        ("staff", True, True),
        ("registered", True, True),
        ("staff", False, False),
        ("registered", False, False),
        (None, False, False),
    ],
)
def test_the_owner_administrators_and_superusers_may_change_it(role, owner, allowed):
    assert slug_edit_allowed(role, owner) is allowed


# --- what is free --------------------------------------------------------------------


async def test_a_new_slug_is_free_and_suggestions_come_with_every_answer(graph):
    check = await check_entry_slug("mas", "le-mas-association-69")
    assert (check["slug"], check["free"], check["reason"]) == ("le-mas-association-69", True, None)
    assert check["suggestions"]
    assert "unafam-association-69" not in check["suggestions"]


async def test_a_slug_another_entry_holds_is_taken(graph):
    check = await check_entry_slug("mas", "unafam-association-69")
    assert (check["free"], check["reason"]) == (False, "taken")


async def test_a_slug_another_entry_used_to_hold_is_taken(graph):
    await give_former("unafam-collectif-69", "other")
    check = await check_entry_slug("mas", "unafam-collectif-69")
    assert (check["free"], check["reason"]) == (False, "taken")


async def test_its_own_current_and_former_slugs_are_free(graph):
    await give_former("le-mas-collectif-69", "mas")
    assert (await check_entry_slug("mas", "le-mas-gem-69"))["free"] is True
    assert (await check_entry_slug("mas", "le-mas-collectif-69"))["free"] is True


async def test_an_invalid_slug_is_said_so(graph):
    check = await check_entry_slug("mas", "Le MAS")
    assert (check["free"], check["reason"]) == (False, "invalid")


# --- the change ----------------------------------------------------------------------


async def test_a_change_leaves_the_old_slug_redirecting_to_the_entry(graph):
    assert await change_entry_slug("mas", "le-mas-association-69", "u-owner") == "le-mas-association-69"
    assert await slug_of(graph, "mas") == "le-mas-association-69"
    assert await former("le-mas-gem-69") == ("mas", "u-owner")


async def test_every_former_slug_leads_to_the_current_one(graph):
    from api.routers.entry_slugs import current_slug

    await change_entry_slug("mas", "le-mas-b-69", "u")
    await change_entry_slug("mas", "le-mas-c-69", "u")
    assert (await current_slug("le-mas-gem-69")).slug == "le-mas-c-69"
    assert (await current_slug("le-mas-b-69")).slug == "le-mas-c-69"


async def test_taking_back_a_former_slug_removes_its_redirect(graph):
    await change_entry_slug("mas", "le-mas-association-69", "u")
    await change_entry_slug("mas", "le-mas-gem-69", "u")
    assert await slug_of(graph, "mas") == "le-mas-gem-69"
    assert await former("le-mas-gem-69") is None
    assert await former("le-mas-association-69") == ("mas", "u")


async def test_an_unchanged_slug_writes_nothing(graph):
    assert await change_entry_slug("mas", "le-mas-gem-69", "u") == "le-mas-gem-69"
    assert await former("le-mas-gem-69") is None


@pytest.mark.parametrize("slug,code", [("unafam-association-69", "taken"), ("Le MAS", "invalid")])
async def test_a_refused_slug_changes_nothing(graph, slug, code):
    with pytest.raises(EntrySlugRefused) as refused:
        await change_entry_slug("mas", slug, "u")
    assert refused.value.code == code
    assert await slug_of(graph, "mas") == "le-mas-gem-69"
    assert await former("le-mas-gem-69") is None


async def test_an_unknown_entry_is_refused(graph):
    with pytest.raises(EntrySlugRefused) as refused:
        await change_entry_slug("nobody", "le-mas-association-69", "u")
    assert refused.value.code == "unknown_entry"
