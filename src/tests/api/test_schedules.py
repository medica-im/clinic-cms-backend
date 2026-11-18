"""The /schedules endpoints: who may write an entry's opening hours, and what
the graph holds afterwards.

Authorization follows the appointments: staff may read, never write something
merely because they are staff; the people connected to the entry may write it.
That rule is mocked here exactly as test_appointments.py mocks it. What is real
is the graph: the point of these tests is that a schedule is one node linked to
its entry, replaced whole by a PUT, and gone on a DELETE.
"""
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

ENTRY = "entry-uid-001"
URL = "/schedules"

LIVE = {
    "entry": ENTRY,
    "channel": "phone",
    "label": "Accueil téléphonique",
    "holidays": "open",
    "days": {str(day): [{"opens": "08:00", "closes": "20:00"}] for day in range(1, 8)},
}

OFFICE_HOURS = {
    "entry": ENTRY,
    "channel": "on_site",
    "label": None,
    "holidays": "closed",
    "days": {
        "1": [{"opens": "08:00", "closes": "12:00"}, {"opens": "14:00", "closes": "18:00"}],
        "2": [{"opens": "08:00", "closes": "12:00"}],
    },
}


@pytest.fixture
async def entry(neo4j_graph):
    await neo4j_graph.cypher_query("CREATE (:Entry {uid: $uid, active: true})", {"uid": ENTRY})
    return ENTRY


async def stored(adb, uid=None):
    rows, _ = await adb.cypher_query(
        "MATCH (:Entry {uid: $entry})-[:HAS_SCHEDULE]->(s:Schedule) "
        "WHERE $uid IS NULL OR s.uid = $uid RETURN properties(s)",
        {"entry": ENTRY, "uid": uid},
    )
    return [row[0] for row in rows]


def signed_in(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt, role, fake_entry, connected):
    stack.enter_context(patch_jwt(jwt))
    stack.enter_context(mock_neo4j_role(role))
    stack.enter_context(mock_get_site)
    stack.enter_context(patch("api.routers.schedule.get_entry", new_callable=AsyncMock, return_value=fake_entry))
    stack.enter_context(
        patch("api.routers.schedule.get_entry_users", new_callable=AsyncMock, return_value=fake_entry.owner._nodes)
    )
    stack.enter_context(
        patch("api.auth.is_user_in_authorized_list", new_callable=AsyncMock, return_value=connected)
    )


async def create(client, adb, patch_jwt, mock_neo4j_role, mock_get_site, jwt_owner, fake_entry, payload=LIVE):
    with ExitStack() as stack:
        signed_in(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_owner, None, fake_entry, True)
        response = await client.post(URL, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


async def test_a_signed_out_caller_cannot_create_a_schedule(client, schedules_acl, entry):
    response = await client.post(URL, json=LIVE)
    assert response.status_code == 401


async def test_the_owner_creates_a_schedule_linked_to_the_entry(
    client, patch_jwt, jwt_owner, mock_neo4j_role, mock_get_site, site, schedules_acl, fake_entry, entry, neo4j_graph
):
    data = await create(client, neo4j_graph, patch_jwt, mock_neo4j_role, mock_get_site, jwt_owner, fake_entry)
    assert data["entry"] == ENTRY
    assert data["channel"] == "phone"
    assert data["holidays"] == "open"
    assert data["days"]["1"] == [{"opens": "08:00", "closes": "20:00"}]
    (node,) = await stored(neo4j_graph, data["uid"])
    assert node["day_1"] == ["08:00-20:00"]
    assert node["label"] == "Accueil téléphonique"


async def test_a_day_without_period_is_stored_as_an_empty_list(
    client, patch_jwt, jwt_owner, mock_neo4j_role, mock_get_site, site, schedules_acl, fake_entry, entry, neo4j_graph
):
    data = await create(
        client, neo4j_graph, patch_jwt, mock_neo4j_role, mock_get_site, jwt_owner, fake_entry, OFFICE_HOURS
    )
    (node,) = await stored(neo4j_graph, data["uid"])
    assert node["day_1"] == ["08:00-12:00", "14:00-18:00"]
    assert node["day_3"] == []
    assert node["day_7"] == []
    assert data["days"]["7"] == []


async def test_a_staff_member_who_is_not_connected_to_the_entry_cannot_write(
    client, patch_jwt, jwt_staff, mock_neo4j_role, mock_get_site, site, schedules_acl, fake_entry, entry, neo4j_graph
):
    with ExitStack() as stack:
        signed_in(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_staff, "staff", fake_entry, False)
        response = await client.post(URL, json=LIVE)
    assert response.status_code == 403
    assert await stored(neo4j_graph) == []


async def test_an_administrator_may_write_any_entry(
    client, patch_jwt, jwt_administrator, mock_neo4j_role, mock_get_site, site, schedules_acl, fake_entry, entry,
    neo4j_graph,
):
    with ExitStack() as stack:
        signed_in(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_administrator, "administrator", fake_entry, False)
        response = await client.post(URL, json=LIVE)
    assert response.status_code == 200
    assert len(await stored(neo4j_graph)) == 1


async def test_an_entry_that_is_not_in_the_graph_is_a_404(
    client, patch_jwt, jwt_owner, mock_neo4j_role, mock_get_site, site, schedules_acl, fake_entry, neo4j_graph
):
    with ExitStack() as stack:
        signed_in(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_owner, None, fake_entry, True)
        response = await client.post(URL, json=LIVE)
    assert response.status_code == 404


async def test_an_invalid_schedule_is_refused_and_not_stored(
    client, patch_jwt, jwt_owner, mock_neo4j_role, mock_get_site, site, schedules_acl, fake_entry, entry, neo4j_graph
):
    bad = {**LIVE, "days": {"1": [{"opens": "12:00", "closes": "08:00"}]}}
    with ExitStack() as stack:
        signed_in(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_owner, None, fake_entry, True)
        response = await client.post(URL, json=bad)
    assert response.status_code == 422
    assert await stored(neo4j_graph) == []


async def test_an_update_replaces_the_whole_schedule(
    client, patch_jwt, jwt_owner, mock_neo4j_role, mock_get_site, site, schedules_acl, fake_entry, entry, neo4j_graph
):
    data = await create(client, neo4j_graph, patch_jwt, mock_neo4j_role, mock_get_site, jwt_owner, fake_entry)
    update = {**OFFICE_HOURS, "channel": "phone", "label": "Accueil"}
    with ExitStack() as stack:
        signed_in(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_owner, None, fake_entry, True)
        response = await client.put(f"{URL}/{data['uid']}", json=update)
    assert response.status_code == 200, response.text
    (node,) = await stored(neo4j_graph)
    assert node["uid"] == data["uid"]
    assert node["day_1"] == ["08:00-12:00", "14:00-18:00"]
    assert node["day_5"] == []
    assert node["holidays"] == "closed"
    assert node["label"] == "Accueil"


async def test_an_update_that_drops_the_label_removes_it(
    client, patch_jwt, jwt_owner, mock_neo4j_role, mock_get_site, site, schedules_acl, fake_entry, entry, neo4j_graph
):
    data = await create(client, neo4j_graph, patch_jwt, mock_neo4j_role, mock_get_site, jwt_owner, fake_entry)
    with ExitStack() as stack:
        signed_in(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_owner, None, fake_entry, True)
        await client.put(f"{URL}/{data['uid']}", json={**LIVE, "label": None})
    (node,) = await stored(neo4j_graph)
    assert "label" not in node


async def test_a_schedule_cannot_be_moved_to_another_entry(
    client, patch_jwt, jwt_owner, mock_neo4j_role, mock_get_site, site, schedules_acl, fake_entry, entry, neo4j_graph
):
    data = await create(client, neo4j_graph, patch_jwt, mock_neo4j_role, mock_get_site, jwt_owner, fake_entry)
    with ExitStack() as stack:
        signed_in(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_owner, None, fake_entry, True)
        response = await client.put(f"{URL}/{data['uid']}", json={**LIVE, "entry": "another-entry"})
    assert response.status_code == 400


async def test_updating_an_unknown_schedule_is_a_404(
    client, patch_jwt, jwt_owner, mock_neo4j_role, mock_get_site, site, schedules_acl, fake_entry, entry
):
    with ExitStack() as stack:
        signed_in(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_owner, None, fake_entry, True)
        response = await client.put(f"{URL}/nope", json=LIVE)
    assert response.status_code == 404


async def test_the_owner_deletes_a_schedule(
    client, patch_jwt, jwt_owner, mock_neo4j_role, mock_get_site, site, schedules_acl, fake_entry, entry, neo4j_graph
):
    data = await create(client, neo4j_graph, patch_jwt, mock_neo4j_role, mock_get_site, jwt_owner, fake_entry)
    with ExitStack() as stack:
        signed_in(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_owner, None, fake_entry, True)
        response = await client.delete(f"{URL}/{data['uid']}")
    assert response.status_code == 200
    assert await stored(neo4j_graph) == []
    rows, _ = await neo4j_graph.cypher_query("MATCH (e:Entry {uid: $uid}) RETURN e.uid", {"uid": ENTRY})
    assert rows == [[ENTRY]]


async def test_a_staff_member_who_is_not_connected_to_the_entry_cannot_delete(
    client, patch_jwt, jwt_owner, jwt_staff, mock_neo4j_role, mock_get_site, site, schedules_acl, fake_entry, entry,
    neo4j_graph,
):
    data = await create(client, neo4j_graph, patch_jwt, mock_neo4j_role, mock_get_site, jwt_owner, fake_entry)
    with ExitStack() as stack:
        signed_in(stack, patch_jwt, mock_neo4j_role, mock_get_site, jwt_staff, "staff", fake_entry, False)
        response = await client.delete(f"{URL}/{data['uid']}")
    assert response.status_code == 403
    assert len(await stored(neo4j_graph)) == 1


async def test_anyone_may_read_the_schedules_of_an_entry(
    client, patch_jwt, jwt_owner, mock_neo4j_role, mock_get_site, site, schedules_acl, fake_entry, entry, neo4j_graph
):
    await create(client, neo4j_graph, patch_jwt, mock_neo4j_role, mock_get_site, jwt_owner, fake_entry, LIVE)
    await create(client, neo4j_graph, patch_jwt, mock_neo4j_role, mock_get_site, jwt_owner, fake_entry, OFFICE_HOURS)
    with ExitStack() as stack:
        stack.enter_context(mock_neo4j_role(None))
        stack.enter_context(mock_get_site)
        response = await client.get(f"/entries/{ENTRY}/schedules")
    assert response.status_code == 200
    body = response.json()
    assert [s["channel"] for s in body] == ["on_site", "phone"]
    assert body[1]["days"]["3"] == [{"opens": "08:00", "closes": "20:00"}]
    assert body[0]["days"]["3"] == []


async def test_an_entry_without_schedule_has_an_empty_list(client, mock_neo4j_role, mock_get_site, site, schedules_acl, entry):
    with ExitStack() as stack:
        stack.enter_context(mock_neo4j_role(None))
        stack.enter_context(mock_get_site)
        response = await client.get(f"/entries/{ENTRY}/schedules")
    assert response.status_code == 200
    assert response.json() == []


async def test_reading_the_schedules_of_an_unknown_entry_is_a_404(
    client, mock_neo4j_role, mock_get_site, site, schedules_acl, neo4j_graph
):
    with ExitStack() as stack:
        stack.enter_context(mock_neo4j_role(None))
        stack.enter_context(mock_get_site)
        response = await client.get("/entries/nope/schedules")
    assert response.status_code == 404
