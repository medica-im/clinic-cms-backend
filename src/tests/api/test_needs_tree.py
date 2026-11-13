"""The needs graph: what a person asks a directory for, as reference data.

A Need is matched by slug, since a uid differs per Neo4j server. A directory
lists a Need through LISTS_NEED, and Situations point at Needs through IMPACTS,
so a Need's slug is what the console's situations file names. Everyone reads the
graph; only a superuser writes it.

A need can sit under several broader ones (housing serves warmth, hygiene and
sleep), so `parents` is a list: a graph with no loop, not a tree.

Nodes that predate the slug have none. The tree still shows them, keyed by uid,
so that the console can see what to adopt; PATCH /needs/by-uid/{uid} gives one
its slug, once.
"""
from contextlib import ExitStack

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

URL = "/needs"
SOIN = {"slug": "soin", "name_fr": "Soin", "definition_fr": "Être soigné."}
SUIVI = {"slug": "suivi-psychologique", "name_fr": "Suivi psychologique", "parents": ["soin"]}
LOGEMENT = {"slug": "logement", "name_fr": "Logement"}


async def edges(adb, slug=None):
    rows, _ = await adb.cypher_query(
        "MATCH (n:Need)-[:PART_OF]->(p:Need) WHERE $slug IS NULL OR n.slug = $slug "
        "RETURN n.slug, p.slug ORDER BY n.slug",
        {"slug": slug},
    )
    return rows


async def stored(adb, slug):
    rows, _ = await adb.cypher_query("MATCH (n:Need {slug: $slug}) RETURN properties(n)", {"slug": slug})
    return [row[0] for row in rows]


def as_role(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt, role="superuser"):
    stack.enter_context(patch_jwt(jwt))
    stack.enter_context(mock_neo4j_role(role))
    stack.enter_context(mock_get_site)


async def post(client, body, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser, path=URL):
    with ExitStack() as stack:
        as_role(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
        return await client.post(path, json=body)


async def patch(client, path, body, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser):
    with ExitStack() as stack:
        as_role(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
        return await client.patch(path, json=body)


async def anonymous_get(client, path, mock_neo4j_role, mock_get_site):
    with ExitStack() as stack:
        stack.enter_context(mock_neo4j_role(None))
        stack.enter_context(mock_get_site)
        return await client.get(path)


@pytest.fixture
async def tree(client, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser, site, needs_acl, neo4j_graph):
    for body in (SOIN, SUIVI, LOGEMENT):
        response = await post(client, body, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
        assert response.status_code == 201, response.text
    return neo4j_graph


async def test_a_signed_out_caller_cannot_create_a_need(client, needs_acl, neo4j_graph):
    assert (await client.post(URL, json=SOIN)).status_code == 401


async def test_an_administrator_cannot_write_the_tree(
    client, patch_jwt, jwt_administrator, mock_neo4j_role, mock_get_site, site, needs_acl, neo4j_graph
):
    with ExitStack() as stack:
        as_role(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_administrator, "administrator")
        response = await client.post(URL, json=SOIN)
    assert response.status_code == 403
    assert await stored(neo4j_graph, "soin") == []


async def test_a_superuser_creates_a_need_and_one_under_it(client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree):
    (soin,) = await stored(tree, "soin")
    assert soin["uid"]
    assert soin["definition_fr"] == "Être soigné."
    assert await edges(tree) == [["suivi-psychologique", "soin"]]


async def test_a_need_is_created_under_several_parents(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    response = await post(client, {"slug": "abri", "name_fr": "Abri", "parents": ["soin", "logement"]},
                          patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 201, response.text
    assert response.json()["parents"] == ["logement", "soin"]
    assert response.json()["uid"]
    assert await edges(tree, "abri") == [["abri", "logement"], ["abri", "soin"]]


async def test_a_slug_already_in_the_graph_is_a_409_and_changes_nothing(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    response = await post(client, {**SOIN, "name_fr": "Autre"}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 409
    (node,) = await stored(tree, "soin")
    assert node["name_fr"] == "Soin"


async def test_an_unknown_parent_is_a_422_and_nothing_is_created(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    response = await post(client, {"slug": "x", "name_fr": "X", "parents": ["soin", "nope"]}, patch_jwt, mock_neo4j_role,
                          mock_get_site, jwt_superuser)
    assert response.status_code == 422
    assert "nope" in response.text
    assert await stored(tree, "x") == []


@pytest.mark.parametrize(
    "body",
    [
        {"slug": "Mauvais Slug", "name_fr": "X"},
        {"slug": "x", "name_fr": " "},
        {"slug": "x", "name_fr": "X", "parents": ["x"]},
    ],
)
async def test_an_invalid_need_is_refused(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, site, needs_acl, neo4j_graph, body
):
    response = await post(client, body, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 422
    assert await stored(neo4j_graph, "x") == []


async def test_anyone_reads_the_tree_by_slug(client, tree, mock_neo4j_role, mock_get_site):
    response = await anonymous_get(client, f"{URL}/tree", mock_neo4j_role, mock_get_site)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [n["slug"] for n in body] == ["logement", "soin", "suivi-psychologique"]
    assert {n["slug"]: n["parents"] for n in body}["suivi-psychologique"] == ["soin"]


async def test_the_tree_names_the_parent_by_uid_too_for_nodes_that_have_no_slug(client, tree, mock_neo4j_role, mock_get_site):
    await tree.cypher_query("MATCH (s:Need {slug: 'soin'}) CREATE (:Need {uid: 'old', name_fr: 'Ancien besoin'})-[:PART_OF]->(s)")
    response = await anonymous_get(client, f"{URL}/tree", mock_neo4j_role, mock_get_site)
    (soin,) = [n for n in response.json() if n["slug"] == "soin"]
    (old,) = [n for n in response.json() if n["uid"] == "old"]
    assert old["parent_uids"] == [soin["uid"]]
    assert old["parents"] == ["soin"]
    assert soin["parent_uids"] == []


async def test_a_need_with_several_parents_is_one_row_that_lists_them_all(client, tree, mock_neo4j_role, mock_get_site):
    """A need under several parents is one row that names them all, by slug and by uid."""
    await tree.cypher_query(
        "MATCH (soin:Need {slug: 'soin'}), (logement:Need {slug: 'logement'}) "
        "CREATE (:Need {uid: 'x', name_fr: 'Écoute'})-[:PART_OF]->(logement), "
        "(:Need {uid: 'x2', name_fr: 'Autre'})-[:PART_OF]->(soin)"
    )
    await tree.cypher_query(
        "MATCH (x:Need {uid: 'x'}), (soin:Need {slug: 'soin'}) CREATE (x)-[:PART_OF]->(soin)"
    )
    response = await anonymous_get(client, f"{URL}/tree", mock_neo4j_role, mock_get_site)
    rows = [n for n in response.json() if n["uid"] == "x"]
    assert len(rows) == 1
    (soin,) = [n for n in response.json() if n["slug"] == "soin"]
    (logement,) = [n for n in response.json() if n["slug"] == "logement"]
    assert rows[0]["parents"] == ["logement", "soin"]
    assert sorted(rows[0]["parent_uids"]) == sorted([logement["uid"], soin["uid"]])
    assert [n["uid"] for n in response.json()].count("x") == 1


async def test_a_need_is_read_by_slug(client, tree, mock_neo4j_role, mock_get_site):
    found = await anonymous_get(client, f"{URL}/suivi-psychologique", mock_neo4j_role, mock_get_site)
    missing = await anonymous_get(client, f"{URL}/nope", mock_neo4j_role, mock_get_site)
    assert found.status_code == 200
    assert found.json()["parents"] == ["soin"]
    assert missing.status_code == 404


async def test_a_patch_changes_only_what_it_sends(client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree):
    response = await patch(client, f"{URL}/suivi-psychologique", {"name_fr": "Suivi"}, patch_jwt, mock_neo4j_role,
                           mock_get_site, jwt_superuser)
    assert response.status_code == 200, response.text
    assert response.json()["name_fr"] == "Suivi"
    assert await edges(tree, "suivi-psychologique") == [["suivi-psychologique", "soin"]]


@pytest.mark.parametrize("parents", [["logement"], ["logement", "soin"]])
async def test_the_parents_sent_replace_the_edges(client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree, parents):
    response = await patch(client, f"{URL}/suivi-psychologique", {"parents": parents}, patch_jwt, mock_neo4j_role,
                           mock_get_site, jwt_superuser)
    assert response.status_code == 200, response.text
    assert response.json()["parents"] == parents
    assert await edges(tree) == [["suivi-psychologique", p] for p in parents]


async def test_no_parents_detaches_the_need_and_null_is_refused(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    refused = await patch(client, f"{URL}/suivi-psychologique", {"parents": None}, patch_jwt, mock_neo4j_role,
                          mock_get_site, jwt_superuser)
    assert refused.status_code == 422
    response = await patch(client, f"{URL}/suivi-psychologique", {"parents": []}, patch_jwt, mock_neo4j_role,
                           mock_get_site, jwt_superuser)
    assert response.json()["parents"] == []
    assert await edges(tree) == []


@pytest.mark.parametrize("slug, parents", [("soin", ["logement", "suivi-psychologique"]), ("soin", ["soin"])])
async def test_a_parent_that_would_make_the_graph_loop_is_a_409(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree, slug, parents
):
    response = await patch(client, f"{URL}/{slug}", {"parents": parents}, patch_jwt, mock_neo4j_role, mock_get_site,
                           jwt_superuser)
    assert response.status_code == 409
    assert await edges(tree) == [["suivi-psychologique", "soin"]]


async def test_patching_an_unknown_need_is_a_404(client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree):
    response = await patch(client, f"{URL}/nope", {"name_fr": "X"}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 404


async def test_the_slug_cannot_be_renamed(client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree):
    response = await patch(client, f"{URL}/soin", {"slug": "perte"}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 422


async def test_a_need_without_a_slug_is_in_the_tree_keyed_by_its_uid(client, tree, mock_neo4j_role, mock_get_site):
    await tree.cypher_query("CREATE (:Need {uid: 'old', name_fr: 'Ancien besoin'})")
    response = await anonymous_get(client, f"{URL}/tree", mock_neo4j_role, mock_get_site)
    (old,) = [n for n in response.json() if n["uid"] == "old"]
    assert old["slug"] is None
    assert old["name_fr"] == "Ancien besoin"
    assert [n["slug"] for n in response.json()][-1] is None


async def test_a_slugless_need_is_given_its_slug_by_uid(client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree):
    await tree.cypher_query("MATCH (s:Need {slug: 'soin'}) CREATE (:Need {uid: 'old', name_fr: 'Ancien besoin'})-[:PART_OF]->(s)")
    response = await patch(client, f"{URL}/by-uid/old", {"slug": "ancien-besoin"}, patch_jwt, mock_neo4j_role,
                           mock_get_site, jwt_superuser)
    assert response.status_code == 200, response.text
    assert response.json()["slug"] == "ancien-besoin"
    assert response.json()["parents"] == ["soin"]
    (node,) = await stored(tree, "ancien-besoin")
    assert node["uid"] == "old"
    assert node["name_fr"] == "Ancien besoin"


async def test_a_need_that_has_a_slug_is_never_renamed_by_uid(client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree):
    (soin,) = await stored(tree, "soin")
    response = await patch(client, f"{URL}/by-uid/{soin['uid']}", {"slug": "autre"}, patch_jwt, mock_neo4j_role,
                           mock_get_site, jwt_superuser)
    assert response.status_code == 409
    assert await stored(tree, "autre") == []


async def test_a_slug_by_uid_that_is_taken_is_a_409(client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree):
    await tree.cypher_query("CREATE (:Need {uid: 'old', name_fr: 'Ancien besoin'})")
    response = await patch(client, f"{URL}/by-uid/old", {"slug": "soin"}, patch_jwt, mock_neo4j_role, mock_get_site,
                           jwt_superuser)
    assert response.status_code == 409


async def test_an_unknown_uid_is_a_404_and_a_bad_slug_a_422(client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree):
    await tree.cypher_query("CREATE (:Need {uid: 'old', name_fr: 'Ancien besoin'})")
    assert (await patch(client, f"{URL}/by-uid/nope", {"slug": "x"}, patch_jwt, mock_neo4j_role, mock_get_site,
                        jwt_superuser)).status_code == 404
    assert (await patch(client, f"{URL}/by-uid/old", {"slug": "Mauvais Slug"}, patch_jwt, mock_neo4j_role,
                        mock_get_site, jwt_superuser)).status_code == 422


async def test_an_administrator_cannot_give_a_slug(client, patch_jwt, jwt_administrator, mock_neo4j_role, mock_get_site, tree):
    await tree.cypher_query("CREATE (:Need {uid: 'old', name_fr: 'Ancien besoin'})")
    with ExitStack() as stack:
        as_role(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_administrator, "administrator")
        response = await client.patch(f"{URL}/by-uid/old", json={"slug": "ancien-besoin"})
    assert response.status_code == 403
