"""The /conditions endpoints: the mental health tree the console seeds.

A Condition is a node of reference data (a DSM-5-TR chapter, or a disorder under
one), matched by slug because the same node has a different uid on each Neo4j
server. Everyone reads the tree; only a superuser writes it, since every
directory's selector is built from it. The graph is real: what these tests pin is
that a parent is one PART_OF edge, replaced rather than added to, and that the
tree stays a tree.
"""
from contextlib import ExitStack

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

URL = "/conditions"
CHAPTER = "troubles-lies-a-une-substance-et-troubles-addictifs"

CHAPTER_BODY = {
    "slug": CHAPTER,
    "name_fr": "Troubles liés à une substance et troubles addictifs",
    "label_fr": "Addictions",
    "kind": "chapter",
    "chapter": 16,
    "icd_11": ["6C4", "6C5"],
    "synonyms_fr": ["dépendance", "toxicomanie"],
}
ALCOOL = {
    "slug": "addiction-alcool",
    "name_fr": "Alcool",
    "icd_11": ["6C40"],
    "synonyms_fr": ["alcoolisme"],
    "chapter": 16,
    "parent": CHAPTER,
}


async def edges(adb, slug=None):
    rows, _ = await adb.cypher_query(
        "MATCH (c:Condition)-[:PART_OF]->(p:Condition) WHERE $slug IS NULL OR c.slug = $slug "
        "RETURN c.slug, p.slug ORDER BY c.slug",
        {"slug": slug},
    )
    return rows


async def stored(adb, slug):
    rows, _ = await adb.cypher_query("MATCH (c:Condition {slug: $slug}) RETURN properties(c)", {"slug": slug})
    return [row[0] for row in rows]


def as_superuser(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser):
    stack.enter_context(patch_jwt(jwt_superuser))
    stack.enter_context(mock_neo4j_role("superuser"))
    stack.enter_context(mock_get_site)


async def post(client, body, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser):
    with ExitStack() as stack:
        as_superuser(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
        return await client.post(URL, json=body)


async def patch(client, slug, body, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser):
    with ExitStack() as stack:
        as_superuser(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
        return await client.patch(f"{URL}/{slug}", json=body)


@pytest.fixture
async def tree(client, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser, site, conditions_acl, neo4j_graph):
    for body in (CHAPTER_BODY, ALCOOL):
        response = await post(client, body, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
        assert response.status_code == 201, response.text
    return neo4j_graph


async def test_a_signed_out_caller_cannot_create_a_condition(client, conditions_acl, neo4j_graph):
    response = await client.post(URL, json=CHAPTER_BODY)
    assert response.status_code == 401


async def test_only_a_superuser_writes_the_tree(
    client, patch_jwt, jwt_administrator, mock_neo4j_role, mock_get_site, site, conditions_acl, neo4j_graph
):
    for role, jwt_name in (("administrator", jwt_administrator),):
        with ExitStack() as stack:
            stack.enter_context(patch_jwt(jwt_name))
            stack.enter_context(mock_neo4j_role(role))
            stack.enter_context(mock_get_site)
            response = await client.post(URL, json=CHAPTER_BODY)
        assert response.status_code == 403
    assert await stored(neo4j_graph, CHAPTER) == []


async def test_a_staff_member_cannot_patch_a_condition(
    client, patch_jwt, jwt_staff, tree, mock_neo4j_role, mock_get_site
):
    with ExitStack() as stack:
        stack.enter_context(patch_jwt(jwt_staff))
        stack.enter_context(mock_neo4j_role("staff"))
        stack.enter_context(mock_get_site)
        response = await client.patch(f"{URL}/addiction-alcool", json={"name_fr": "Autre"})
    assert response.status_code == 403
    (node,) = await stored(tree, "addiction-alcool")
    assert node["name_fr"] == "Alcool"


async def test_a_superuser_creates_a_chapter_and_a_condition_under_it(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, site, conditions_acl, neo4j_graph
):
    chapter = await post(client, CHAPTER_BODY, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert chapter.status_code == 201, chapter.text
    assert chapter.json()["parent"] is None
    condition = await post(client, ALCOOL, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert condition.status_code == 201, condition.text
    body = condition.json()
    assert body["parent"] == CHAPTER
    assert body["uid"]
    assert body["icd_11"] == ["6C40"]
    assert await edges(neo4j_graph) == [["addiction-alcool", CHAPTER]]
    (node,) = await stored(neo4j_graph, "addiction-alcool")
    assert node["synonyms_fr"] == ["alcoolisme"]
    assert node["uid"] == body["uid"]


async def test_a_slug_already_in_the_graph_is_a_409_and_changes_nothing(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    response = await post(
        client, {**ALCOOL, "name_fr": "Autre"}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser
    )
    assert response.status_code == 409
    (node,) = await stored(tree, "addiction-alcool")
    assert node["name_fr"] == "Alcool"


async def test_an_unknown_parent_is_refused_and_nothing_is_created(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, site, conditions_acl, neo4j_graph
):
    response = await post(client, ALCOOL, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 422
    assert await stored(neo4j_graph, "addiction-alcool") == []


async def test_an_invalid_condition_is_refused(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, site, conditions_acl, neo4j_graph
):
    response = await post(
        client, {**ALCOOL, "icd_11": ["F32"]}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser
    )
    assert response.status_code == 422


async def test_anyone_reads_the_tree_chapters_first(client, tree, mock_neo4j_role, mock_get_site):
    await tree.cypher_query("CREATE (:Condition {uid: 'x', slug: 'douleur', name_fr: 'Douleur', kind: 'condition'})")
    with ExitStack() as stack:
        stack.enter_context(mock_neo4j_role(None))
        stack.enter_context(mock_get_site)
        response = await client.get(URL)
    assert response.status_code == 200
    body = response.json()
    assert [c["slug"] for c in body] == [CHAPTER, "addiction-alcool", "douleur"]
    assert body[1]["parent"] == CHAPTER
    assert body[0]["synonyms_fr"] == ["dépendance", "toxicomanie"]
    assert body[2]["icd_11"] == []


async def test_a_condition_is_read_by_slug(client, tree, mock_neo4j_role, mock_get_site):
    with ExitStack() as stack:
        stack.enter_context(mock_neo4j_role(None))
        stack.enter_context(mock_get_site)
        found = await client.get(f"{URL}/addiction-alcool")
        missing = await client.get(f"{URL}/nope")
    assert found.status_code == 200
    assert found.json()["name_fr"] == "Alcool"
    assert missing.status_code == 404


async def test_a_patch_changes_only_what_it_sends(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    response = await patch(
        client, "addiction-alcool", {"name_fr": "Alcool (usage)"}, patch_jwt, mock_neo4j_role, mock_get_site,
        jwt_superuser,
    )
    assert response.status_code == 200, response.text
    assert response.json()["name_fr"] == "Alcool (usage)"
    (node,) = await stored(tree, "addiction-alcool")
    assert node["icd_11"] == ["6C40"]
    assert node["synonyms_fr"] == ["alcoolisme"]
    assert await edges(tree, "addiction-alcool") == [["addiction-alcool", CHAPTER]]


async def test_a_patch_replaces_the_synonyms_it_sends(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    response = await patch(
        client, "addiction-alcool", {"synonyms_fr": ["alcoolodépendance"]}, patch_jwt, mock_neo4j_role,
        mock_get_site, jwt_superuser,
    )
    assert response.status_code == 200
    (node,) = await stored(tree, "addiction-alcool")
    assert node["synonyms_fr"] == ["alcoolodépendance"]


async def test_changing_the_parent_replaces_the_edge_instead_of_adding_one(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    other = {"slug": "troubles-neurodeveloppementaux", "name_fr": "Troubles neurodéveloppementaux",
             "kind": "chapter", "chapter": 1}
    assert (await post(client, other, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)).status_code == 201
    response = await patch(
        client, "addiction-alcool", {"parent": "troubles-neurodeveloppementaux"}, patch_jwt, mock_neo4j_role,
        mock_get_site, jwt_superuser,
    )
    assert response.status_code == 200, response.text
    assert response.json()["parent"] == "troubles-neurodeveloppementaux"
    assert await edges(tree, "addiction-alcool") == [["addiction-alcool", "troubles-neurodeveloppementaux"]]


async def test_a_null_parent_detaches_the_condition(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    response = await patch(
        client, "addiction-alcool", {"parent": None}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser
    )
    assert response.status_code == 200
    assert response.json()["parent"] is None
    assert await edges(tree, "addiction-alcool") == []


async def test_a_patch_without_parent_leaves_the_edge_alone(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    await patch(client, "addiction-alcool", {"name_fr": "X"}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert await edges(tree, "addiction-alcool") == [["addiction-alcool", CHAPTER]]


async def test_a_parent_that_would_make_a_cycle_is_a_409(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    response = await patch(
        client, CHAPTER, {"parent": "addiction-alcool"}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser
    )
    assert response.status_code == 409
    assert await edges(tree) == [["addiction-alcool", CHAPTER]]


async def test_a_condition_cannot_become_its_own_parent(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    response = await patch(
        client, "addiction-alcool", {"parent": "addiction-alcool"}, patch_jwt, mock_neo4j_role, mock_get_site,
        jwt_superuser,
    )
    assert response.status_code == 409


async def test_patching_an_unknown_condition_is_a_404(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    response = await patch(client, "nope", {"name_fr": "X"}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 404


async def test_patching_the_parent_to_an_unknown_slug_is_a_422(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    response = await patch(
        client, "addiction-alcool", {"parent": "nope"}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser
    )
    assert response.status_code == 422
    assert await edges(tree, "addiction-alcool") == [["addiction-alcool", CHAPTER]]


async def labels(adb, slug):
    rows, _ = await adb.cypher_query("MATCH (c:Condition {slug: $slug}) RETURN labels(c)", {"slug": slug})
    return sorted(rows[0][0])


async def test_a_chapter_also_carries_the_chapter_label_and_a_condition_does_not(tree):
    assert await labels(tree, CHAPTER) == ["Chapter", "Condition"]
    assert await labels(tree, "addiction-alcool") == ["Condition"]


async def test_the_chapter_label_follows_the_kind_when_it_changes(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    response = await patch(
        client, "addiction-alcool", {"kind": "chapter", "chapter": 16, "parent": None}, patch_jwt, mock_neo4j_role,
        mock_get_site, jwt_superuser,
    )
    assert response.status_code == 200, response.text
    assert await labels(tree, "addiction-alcool") == ["Chapter", "Condition"]
    response = await patch(
        client, "addiction-alcool", {"kind": "condition"}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser
    )
    assert response.status_code == 200
    assert await labels(tree, "addiction-alcool") == ["Condition"]


async def test_a_condition_with_a_parent_cannot_become_a_chapter(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    response = await patch(
        client, "addiction-alcool", {"kind": "chapter", "chapter": 16}, patch_jwt, mock_neo4j_role, mock_get_site,
        jwt_superuser,
    )
    assert response.status_code == 409
    assert await labels(tree, "addiction-alcool") == ["Condition"]


async def test_a_chapter_cannot_be_given_a_parent(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, tree
):
    other = {"slug": "troubles-depressifs", "name_fr": "Troubles dépressifs", "kind": "chapter", "chapter": 4}
    assert (await post(client, other, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)).status_code == 201
    response = await patch(
        client, CHAPTER, {"parent": "troubles-depressifs"}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser
    )
    assert response.status_code == 409
    assert await edges(tree, CHAPTER) == []


# What a condition may lead to ("voir aussi": a situation or another condition)
# and the needs it impacts. Links point at nodes by slug; sending a list replaces
# the condition's links of that kind, as a parent is replaced.


async def links(adb, slug, rel):
    rows, _ = await adb.cypher_query(
        f"MATCH (c:Condition {{slug: $slug}})-[:{rel}]->(t) RETURN t.slug ORDER BY t.slug", {"slug": slug}
    )
    return [row[0] for row in rows]


@pytest.fixture
async def targets(tree):
    await tree.cypher_query(
        "CREATE (:Situation {uid: 's1', slug: 'crise-suicidaire', name_fr: 'Crise suicidaire'}), "
        "(:Situation {uid: 's2', slug: 'isolement', name_fr: 'Isolement'}), "
        "(:Situation {uid: 's3', name_fr: 'Sans slug'}), "
        "(:Need {uid: 'n1', slug: 'sante-mentale', name_fr: 'Santé mentale'}), "
        "(:Need {uid: 'n2', slug: 'vivre', name_fr: 'Vivre'})"
    )
    return tree


async def test_a_new_condition_is_created_with_what_it_leads_to_and_impacts(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, targets
):
    body = {**ALCOOL, "slug": "addiction-cannabis", "name_fr": "Cannabis", "icd_11": ["6C41"], "synonyms_fr": [],
            "may_lead_to": ["crise-suicidaire", "addiction-alcool"], "impacts": ["sante-mentale"]}
    response = await post(client, body, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 201, response.text
    assert response.json()["may_lead_to"] == ["addiction-alcool", "crise-suicidaire"]
    assert response.json()["impacts"] == ["sante-mentale"]
    assert await links(targets, "addiction-cannabis", "MAY_LEAD_TO") == ["addiction-alcool", "crise-suicidaire"]
    assert await links(targets, "addiction-cannabis", "IMPACTS") == ["sante-mentale"]


async def test_the_tree_shows_each_condition_s_links(client, targets, mock_neo4j_role, mock_get_site):
    await targets.cypher_query(
        "MATCH (c:Condition {slug: 'addiction-alcool'}), (s:Situation {slug: 'crise-suicidaire'}), "
        "(u:Situation {name_fr: 'Sans slug'}), (n:Need {slug: 'vivre'}) "
        "CREATE (c)-[:MAY_LEAD_TO]->(s), (c)-[:MAY_LEAD_TO]->(u), (c)-[:IMPACTS]->(n)"
    )
    with ExitStack() as stack:
        stack.enter_context(mock_neo4j_role(None))
        stack.enter_context(mock_get_site)
        body = {c["slug"]: c for c in (await client.get(URL)).json()}
    assert body["addiction-alcool"]["may_lead_to"] == ["crise-suicidaire"]
    assert body["addiction-alcool"]["impacts"] == ["vivre"]
    assert body[CHAPTER]["may_lead_to"] == []


async def test_a_patch_replaces_the_links_it_sends_and_keeps_the_others(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, targets
):
    first = await patch(client, "addiction-alcool", {"may_lead_to": ["isolement"], "impacts": ["vivre"]},
                        patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert first.status_code == 200, first.text
    second = await patch(client, "addiction-alcool", {"may_lead_to": ["crise-suicidaire"]},
                         patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert second.status_code == 200, second.text
    assert await links(targets, "addiction-alcool", "MAY_LEAD_TO") == ["crise-suicidaire"]
    assert await links(targets, "addiction-alcool", "IMPACTS") == ["vivre"]
    assert await edges(targets, "addiction-alcool") == [["addiction-alcool", CHAPTER]]


async def test_an_empty_list_removes_the_links(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, targets
):
    await patch(client, "addiction-alcool", {"impacts": ["vivre"]}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    response = await patch(client, "addiction-alcool", {"impacts": []}, patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 200
    assert await links(targets, "addiction-alcool", "IMPACTS") == []


async def test_a_link_to_an_unknown_node_is_a_422_and_writes_nothing(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, targets
):
    to_nothing = await patch(client, "addiction-alcool", {"may_lead_to": ["crise-suicidaire", "nope"]},
                             patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    to_a_situation_as_need = await patch(client, "addiction-alcool", {"impacts": ["isolement"]},
                                         patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert to_nothing.status_code == 422
    assert "nope" in to_nothing.text
    assert to_a_situation_as_need.status_code == 422
    assert await links(targets, "addiction-alcool", "MAY_LEAD_TO") == []


async def test_a_condition_cannot_lead_to_itself(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, targets
):
    response = await patch(client, "addiction-alcool", {"may_lead_to": ["addiction-alcool"]},
                           patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 422


async def test_null_links_are_refused(
    client, patch_jwt, jwt_superuser, mock_neo4j_role, mock_get_site, targets
):
    response = await patch(client, "addiction-alcool", {"may_lead_to": None},
                           patch_jwt, mock_neo4j_role, mock_get_site, jwt_superuser)
    assert response.status_code == 422
