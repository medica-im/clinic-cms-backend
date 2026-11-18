"""The situations tree: reference data the console writes, as it writes conditions.

A Situation is a life circumstance someone comes for (a bereavement, a crisis, a
family in difficulty). It is matched by slug, since a uid differs per Neo4j
server. Three kinds of edge leave it, and each answers a different question:

* PART_OF, at most one: where it sits in the selector's tree;
* MAY_LEAD_TO, to other situations: the "voir aussi" of /concerns;
* IMPACTS, to Needs: what makes a directory listing a Need list it.

Everyone reads the tree; only a superuser writes it, because every directory's
selector is built from it. The legacy GET /situations (a directory's situations
with their entries) is a different view and is left as it is.
"""
from contextlib import ExitStack

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

URL = "/situations"
DEUIL = {
    "slug": "deuil",
    "name_fr": "Deuil",
    "definition_fr": "La perte d'un proche.",
    "synonyms_fr": ["perte d'un proche", " ", "Perte d'un proche"],
}
DEUIL_PERINATAL = {"slug": "deuil-perinatal", "name_fr": "Deuil périnatal", "parent": "deuil"}
ISOLEMENT = {"slug": "isolement", "name_fr": "Isolement social"}


async def edges(adb, rel, slug=None):
    rows, _ = await adb.cypher_query(
        f"MATCH (s:Situation)-[:{rel}]->(x) WHERE $slug IS NULL OR s.slug = $slug "
        "RETURN s.slug, x.slug ORDER BY s.slug, x.slug",
        {"slug": slug},
    )
    return rows


async def stored(adb, slug):
    rows, _ = await adb.cypher_query("MATCH (s:Situation {slug: $slug}) RETURN properties(s)", {"slug": slug})
    return [row[0] for row in rows]


def as_role(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt, role="superuser"):
    stack.enter_context(patch_jwt(jwt))
    stack.enter_context(mock_neo4j_role(role))
    stack.enter_context(mock_get_site)


async def post(client, body, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser):
    with ExitStack() as stack:
        as_role(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
        return await client.post(URL, json=body)


async def patch(client, slug, body, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser):
    with ExitStack() as stack:
        as_role(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
        return await client.patch(f"{URL}/{slug}", json=body)


async def anonymous_get(client, path, mock_neo4j_role, mock_get_site):
    with ExitStack() as stack:
        stack.enter_context(mock_neo4j_role(None))
        stack.enter_context(mock_get_site)
        return await client.get(path)


@pytest.fixture
async def tree(client, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser, site, situations_acl, neo4j_graph):
    await neo4j_graph.cypher_query(
        "CREATE (:Need {uid: 'n1', slug: 'sante-mentale', name_fr: 'Santé mentale'}),"
        " (:Need {uid: 'n2', slug: 'lien-social', name_fr: 'Lien social'})"
    )
    for body in (DEUIL, DEUIL_PERINATAL, ISOLEMENT):
        response = await post(client, body, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
        assert response.status_code == 201, response.text
    return neo4j_graph


async def test_a_signed_out_caller_cannot_create_a_situation(client, situations_acl, neo4j_graph):
    response = await client.post(URL, json=DEUIL)
    assert response.status_code == 401


async def test_an_administrator_cannot_write_the_tree(
    client, patch_jwt, jwt_administrator, mock_neo4j_role, mock_get_site, site, situations_acl, neo4j_graph
):
    with ExitStack() as stack:
        as_role(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_administrator, "administrator")
        response = await client.post(URL, json=DEUIL)
    assert response.status_code == 403
    assert await stored(neo4j_graph, "deuil") == []


async def test_a_staff_member_cannot_patch_a_situation(client, patch_jwt, jwt_staff, tree, mock_neo4j_role, mock_get_site):
    with ExitStack() as stack:
        as_role(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_staff, "staff")
        response = await client.patch(f"{URL}/deuil", json={"name_fr": "Autre"})
    assert response.status_code == 403
    (node,) = await stored(tree, "deuil")
    assert node["name_fr"] == "Deuil"


async def test_a_superuser_creates_a_situation_and_one_under_it(tree):
    (deuil,) = await stored(tree, "deuil")
    assert deuil["uid"]
    assert deuil["definition_fr"] == "La perte d'un proche."
    assert deuil["synonyms_fr"] == ["perte d'un proche"]
    assert await edges(tree, "PART_OF") == [["deuil-perinatal", "deuil"]]


async def test_the_created_situation_is_returned_with_its_edges(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    body = {"slug": "veuvage", "name_fr": "Veuvage", "parent": "deuil", "may_lead_to": ["isolement"],
            "impacts": ["sante-mentale"]}
    response = await post(client, body, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["uid"]
    assert created["parent"] == "deuil"
    assert created["may_lead_to"] == ["isolement"]
    assert created["impacts"] == ["sante-mentale"]
    assert await edges(tree, "MAY_LEAD_TO", "veuvage") == [["veuvage", "isolement"]]
    assert await edges(tree, "IMPACTS", "veuvage") == [["veuvage", "sante-mentale"]]


async def test_a_slug_already_in_the_graph_is_a_409_and_changes_nothing(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    response = await post(client, {**DEUIL, "name_fr": "Autre"}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 409
    (node,) = await stored(tree, "deuil")
    assert node["name_fr"] == "Deuil"


@pytest.mark.parametrize(
    "extra, unknown",
    [
        ({"parent": "nope"}, "nope"),
        ({"may_lead_to": ["isolement", "nope"]}, "nope"),
        ({"impacts": ["nope"]}, "nope"),
    ],
)
async def test_an_unknown_target_is_a_422_and_nothing_is_created(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree, extra, unknown
):
    body = {"slug": "veuvage", "name_fr": "Veuvage", **extra}
    response = await post(client, body, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 422
    assert unknown in response.text
    assert await stored(tree, "veuvage") == []


@pytest.mark.parametrize(
    "body",
    [
        {"slug": "Deuil Récent", "name_fr": "Deuil récent"},
        {"slug": "deuil-recent", "name_fr": "  "},
        {"slug": "deuil-recent", "name_fr": "Deuil récent", "parent": "deuil-recent"},
        {"slug": "deuil-recent", "name_fr": "Deuil récent", "may_lead_to": ["deuil-recent"]},
    ],
)
async def test_an_invalid_situation_is_refused(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, site, situations_acl, neo4j_graph, body
):
    response = await post(client, body, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 422
    assert await stored(neo4j_graph, "deuil-recent") == []


async def test_anyone_reads_the_whole_tree_with_its_edges(client, patch_jwt, jwt_superuser, tree, mock_neo4j_role, mock_get_site):
    await patch(client, "deuil", {"may_lead_to": ["isolement"], "impacts": ["sante-mentale", "lien-social"]},
                patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    response = await anonymous_get(client, f"{URL}/tree", mock_neo4j_role, mock_get_site)
    assert response.status_code == 200, response.text
    by_slug = {s["slug"]: s for s in response.json()}
    assert list(by_slug) == ["deuil", "deuil-perinatal", "isolement"]
    assert by_slug["deuil"]["parent"] is None
    assert by_slug["deuil"]["may_lead_to"] == ["isolement"]
    assert by_slug["deuil"]["impacts"] == ["lien-social", "sante-mentale"]
    assert by_slug["deuil-perinatal"]["parent"] == "deuil"
    assert by_slug["isolement"]["synonyms_fr"] == []


async def test_a_situation_without_a_slug_is_in_the_tree_keyed_by_its_uid(client, tree, mock_neo4j_role, mock_get_site):
    await tree.cypher_query("CREATE (:Situation {uid: 'legacy', name_fr: 'Ancienne situation'})")
    response = await anonymous_get(client, f"{URL}/tree", mock_neo4j_role, mock_get_site)
    (legacy,) = [s for s in response.json() if s["uid"] == "legacy"]
    assert legacy["slug"] is None
    assert legacy["name_fr"] == "Ancienne situation"
    assert [s["slug"] for s in response.json()][-1] is None


async def test_a_slugless_situation_is_given_its_slug_by_uid(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    await tree.cypher_query(
        "MATCH (p:Situation {slug: 'deuil'}), (n:Need {slug: 'lien-social'}) "
        "CREATE (l:Situation {uid: 'legacy', name_fr: 'Ancienne situation'}), "
        "(l)-[:PART_OF]->(p), (l)-[:IMPACTS]->(n)"
    )
    response = await patch(client, f"by-uid/legacy", {"slug": "ancienne-situation"}, patch_jwt,
                           mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 200, response.text
    assert response.json()["slug"] == "ancienne-situation"
    assert response.json()["parent"] == "deuil"
    assert response.json()["impacts"] == ["lien-social"]
    (node,) = await stored(tree, "ancienne-situation")
    assert node["uid"] == "legacy"


async def test_a_situation_that_has_a_slug_is_never_renamed_by_uid(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    (deuil,) = await stored(tree, "deuil")
    response = await patch(client, f"by-uid/{deuil['uid']}", {"slug": "perte"}, patch_jwt, mock_neo4j_role,
                           mock_get_site, jwt_superuser)
    assert response.status_code == 409
    assert await stored(tree, "perte") == []


async def test_a_slug_by_uid_that_is_taken_is_a_409_and_an_unknown_uid_a_404(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    await tree.cypher_query("CREATE (:Situation {uid: 'legacy', name_fr: 'Ancienne situation'})")
    taken = await patch(client, f"by-uid/legacy", {"slug": "deuil"}, patch_jwt, mock_neo4j_role, mock_get_site,
                        jwt_superuser)
    unknown = await patch(client, f"by-uid/nope", {"slug": "x"}, patch_jwt, mock_neo4j_role, mock_get_site,
                          jwt_superuser)
    assert (taken.status_code, unknown.status_code) == (409, 404)


async def test_the_tree_also_names_every_link_by_uid_for_nodes_that_have_no_slug(
    client, tree, mock_neo4j_role, mock_get_site
):
    await tree.cypher_query(
        "MATCH (p:Situation {slug: 'deuil'}) "
        "CREATE (a:Situation {uid: 'a', name_fr: 'A'})-[:PART_OF]->(p), "
        "(a)-[:MAY_LEAD_TO]->(:Situation {uid: 'b', name_fr: 'B'}), "
        "(a)-[:IMPACTS]->(:Need {uid: 'n-old', name_fr: 'Ancien besoin'})"
    )
    response = await anonymous_get(client, f"{URL}/tree", mock_neo4j_role, mock_get_site)
    (a,) = [s for s in response.json() if s["uid"] == "a"]
    (deuil,) = [s for s in response.json() if s["slug"] == "deuil"]
    assert (a["slug"], a["parent"], a["may_lead_to"], a["impacts"]) == (None, "deuil", [], [])
    assert a["parent_uid"] == deuil["uid"]
    assert a["may_lead_to_uids"] == ["b"]
    assert a["impacts_uids"] == ["n-old"]


async def test_a_situation_with_several_parents_is_one_row_that_lists_them_all(client, tree, mock_neo4j_role, mock_get_site):
    await tree.cypher_query(
        "MATCH (a:Situation {slug: 'deuil'}), (b:Situation {slug: 'isolement'}) "
        "CREATE (x:Situation {uid: 'x', name_fr: 'Veuvage'})-[:PART_OF]->(a), (x)-[:PART_OF]->(b)"
    )
    response = await anonymous_get(client, f"{URL}/tree", mock_neo4j_role, mock_get_site)
    rows = [s for s in response.json() if s["uid"] == "x"]
    assert len(rows) == 1
    assert rows[0]["parent"] == "deuil"
    assert len(rows[0]["parent_uids"]) == 2


async def test_a_situation_is_read_by_slug(client, tree, mock_neo4j_role, mock_get_site):
    found = await anonymous_get(client, f"{URL}/deuil-perinatal", mock_neo4j_role, mock_get_site)
    missing = await anonymous_get(client, f"{URL}/nope", mock_neo4j_role, mock_get_site)
    assert found.status_code == 200
    assert found.json()["parent"] == "deuil"
    assert missing.status_code == 404


async def test_a_patch_changes_only_what_it_sends(client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree):
    await patch(client, "deuil-perinatal", {"impacts": ["sante-mentale"]}, patch_jwt, mock_neo4j_role, mock_get_site,
                jwt_superuser)
    response = await patch(client, "deuil-perinatal", {"name_fr": "Deuil d'un bébé"}, patch_jwt, mock_neo4j_role,
                           mock_get_site, jwt_superuser)
    assert response.status_code == 200, response.text
    assert response.json()["name_fr"] == "Deuil d'un bébé"
    assert await edges(tree, "PART_OF", "deuil-perinatal") == [["deuil-perinatal", "deuil"]]
    assert await edges(tree, "IMPACTS", "deuil-perinatal") == [["deuil-perinatal", "sante-mentale"]]


@pytest.mark.parametrize("rel, field, first, second", [
    ("MAY_LEAD_TO", "may_lead_to", ["isolement"], ["deuil-perinatal"]),
    ("IMPACTS", "impacts", ["sante-mentale"], ["lien-social"]),
])
async def test_a_patch_replaces_the_edges_it_sends(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree, rel, field, first, second
):
    await patch(client, "deuil", {field: first}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    response = await patch(client, "deuil", {field: second}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 200, response.text
    assert response.json()[field] == second
    assert await edges(tree, rel, "deuil") == [["deuil", second[0]]]
    cleared = await patch(client, "deuil", {field: []}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert cleared.json()[field] == []
    assert await edges(tree, rel, "deuil") == []


async def test_two_situations_may_lead_to_each_other(client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree):
    await patch(client, "deuil", {"may_lead_to": ["isolement"]}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    response = await patch(client, "isolement", {"may_lead_to": ["deuil"]}, patch_jwt, mock_neo4j_role, mock_get_site,
                           jwt_superuser)
    assert response.status_code == 200
    assert await edges(tree, "MAY_LEAD_TO") == [["deuil", "isolement"], ["isolement", "deuil"]]


async def test_an_unknown_target_in_a_patch_is_a_422_and_changes_nothing(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    await patch(client, "deuil", {"impacts": ["sante-mentale"]}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    response = await patch(client, "deuil", {"name_fr": "X", "impacts": ["nope"]}, patch_jwt, mock_neo4j_role,
                           mock_get_site, jwt_superuser)
    assert response.status_code == 422
    (node,) = await stored(tree, "deuil")
    assert node["name_fr"] == "Deuil"
    assert await edges(tree, "IMPACTS", "deuil") == [["deuil", "sante-mentale"]]


async def test_a_situation_cannot_lead_to_itself(client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree):
    response = await patch(client, "deuil", {"may_lead_to": ["deuil"]}, patch_jwt, mock_neo4j_role, mock_get_site,
                           jwt_superuser)
    assert response.status_code == 422
    assert await edges(tree, "MAY_LEAD_TO") == []


async def test_changing_the_parent_replaces_the_edge(client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree):
    response = await patch(client, "deuil-perinatal", {"parent": "isolement"}, patch_jwt, mock_neo4j_role,
                           mock_get_site, jwt_superuser)
    assert response.status_code == 200, response.text
    assert await edges(tree, "PART_OF", "deuil-perinatal") == [["deuil-perinatal", "isolement"]]


async def test_a_null_parent_detaches_the_situation(client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree):
    response = await patch(client, "deuil-perinatal", {"parent": None}, patch_jwt, mock_neo4j_role, mock_get_site,
                           jwt_superuser)
    assert response.status_code == 200
    assert response.json()["parent"] is None
    assert await edges(tree, "PART_OF") == []


@pytest.mark.parametrize("slug, parent", [("deuil", "deuil-perinatal"), ("deuil", "deuil")])
async def test_a_parent_that_would_make_the_tree_loop_is_a_409(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree, slug, parent
):
    response = await patch(client, slug, {"parent": parent}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 409
    assert await edges(tree, "PART_OF") == [["deuil-perinatal", "deuil"]]


async def test_patching_an_unknown_situation_is_a_404(client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree):
    response = await patch(client, "nope", {"name_fr": "X"}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 404


async def test_the_slug_cannot_be_renamed(client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree):
    response = await patch(client, "deuil", {"slug": "perte"}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 422
    assert await stored(tree, "deuil")


async def test_a_written_situation_is_offered_by_concerns_with_its_see_also(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    from directory.concerns import concerns_of_directory

    await patch(client, "deuil-perinatal", {"may_lead_to": ["isolement"]}, patch_jwt, mock_neo4j_role, mock_get_site,
                jwt_superuser)
    await tree.cypher_query(
        "CREATE (d:Directory {name: 'sm'}),"
        " (d)-[:HAS_ENTRY]->(e:Entry {uid: 'e1', active: true}),"
        " (d)-[:HAS_ENTRY]->(i:Entry {uid: 'e2', active: true})"
        " WITH e, i MATCH (p:Situation {slug: 'deuil-perinatal'}), (s:Situation {slug: 'isolement'})"
        " CREATE (e)-[:MANAGES]->(p), (i)-[:MANAGES]->(s)"
    )
    offered = {c["slug"]: c for c in await concerns_of_directory("sm")}
    assert offered["deuil"]["entries"] == ["e1"]
    assert offered["deuil-perinatal"]["parent"] == offered["deuil"]["uid"]
    assert offered["deuil-perinatal"]["see_also"] == [offered["isolement"]["uid"]]
