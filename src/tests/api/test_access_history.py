"""The access-history endpoint, over HTTP.

test_role_change.py already checks that a superseded Access survives a role
change, but it does so by calling `access_graph.access_history()` directly. A
graph function that returns the right rows says nothing about whether the route
in front of it answers at all: everything between the two — the JWT dependency,
`authorize_api`, the Entry lookup and `AccessHistoryOut` — is skipped by that
kind of test.

That gap is not hypothetical. The history section on the user detail page went
blank in every containerised environment while both graph-level tests stayed
green, because the endpoint was answering 401 to the caller the page used and
nothing asserted on a status code. The frontend swallowed the refusal into an
empty list, so a broken audit trail rendered as an empty one — the failure mode
that makes this endpoint worth testing at the boundary rather than under it.

So these tests go through `versioned_client` and assert on the response: what
an authorised caller gets, what an anonymous one gets, and that the answer is
scoped to the site it was asked about.
"""
import time
import uuid

import pytest
import pytest_asyncio

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


ENTRY_UID = uuid.uuid4().hex

# A second site, to prove the history is scoped. Its Entry exists in the graph
# but has no Organization row: nothing in these tests requests it as the
# current site, and the accesses hung from it must not appear in this site's
# answer.
OTHER_ENTRY_UID = uuid.uuid4().hex


@pytest.fixture(autouse=True)
def users_acl(transactional_db, roles):
    """AccessControl rows for users_v2.

    Autouse for the same reason as in test_role_change.py: without them
    `may_authorize` refuses everybody and a 200-expecting test would fail while
    a 401-expecting one passed for the wrong reason.
    """
    from access.models import Endpoint, AccessControl

    endpoint, _ = Endpoint.objects.get_or_create(name="users_v2")
    permissions = {
        "superuser": 15,
        "administrator": 15,
        "staff": 3,
        "registered": 1,
        "anonymous": 1,
    }
    for role_name, perm in permissions.items():
        AccessControl.objects.get_or_create(
            endpoint=endpoint,
            role=roles[role_name],
            defaults={"permissions": perm},
        )


@pytest_asyncio.fixture(autouse=True)
async def organization(neo4j_graph, site, transactional_db):
    """The site's Organization and Entry, plus a second Entry to scope against."""
    from facility.models import Organization

    await neo4j_graph.cypher_query(
        "CREATE (e:Entry {uid: $uid})", {"uid": ENTRY_UID}
    )
    await neo4j_graph.cypher_query(
        "CREATE (e:Entry {uid: $uid})", {"uid": OTHER_ENTRY_UID}
    )
    await Organization.objects.acreate(
        name="Test Org", site=site, neomodel_uid=ENTRY_UID
    )


class SeededUser:
    def __init__(self, uid, sub):
        self.uid = uid
        self.sub = sub


@pytest_asyncio.fixture(autouse=True)
async def caller_identities(organization, request):
    """A User, Account and Access for each JWT fixture.

    The endpoint resolves the caller through their Account sub, so a test that
    only patches a JWT is asking as somebody the graph has never heard of.
    """
    seeded = {}
    for role in ("superuser", "administrator", "staff", "registered"):
        jwt = request.getfixturevalue(f"jwt_{role}")
        seeded[role] = await _seed_user(role=role, sub=jwt["sub"])
    return seeded


async def _seed_user(role, sub=None, entry_uid=ENTRY_UID):
    """A User with an Account and one active Access on `entry_uid`."""
    from neomodel import adb

    user_uid = uuid.uuid4().hex
    sub = sub or f"sub-{user_uid}"
    now = 1_600_000_000_000

    await adb.cypher_query(
        """
        MATCH (e:Entry {uid: $entry_uid})
        OPTIONAL MATCH (old_a:Account {sub: $sub})<-[:HAS_ACCOUNT]-(old_u:User)
        OPTIONAL MATCH (old_u)-[:HAS_ACCESS]->(old_ac:Access)-[:ACCESS_TO]->(e)
        DETACH DELETE old_a, old_u, old_ac

        WITH e
        CREATE (u:User {uid: $user_uid, email: $email, name: $name, createdAt: $now})
        CREATE (a:Account {uid: $account_uid, sub: $sub, createdAt: $now})
        CREATE (u)-[:HAS_ACCOUNT]->(a)
        CREATE (ac:Access {
            uid: $access_uid, role: $role, active: true, createdAt: $now
        })
        CREATE (u)-[:HAS_ACCESS]->(ac)
        CREATE (ac)-[:ACCESS_TO]->(e)
        """,
        {
            "entry_uid": entry_uid,
            "user_uid": user_uid,
            "account_uid": uuid.uuid4().hex,
            "access_uid": uuid.uuid4().hex,
            "sub": sub,
            "email": f"{user_uid}@example.com",
            "name": f"User {user_uid[:8]}",
            "role": role,
            "now": now,
        },
    )
    return SeededUser(user_uid, sub)


async def test_the_endpoint_answers_an_authorised_caller(
    versioned_client, patch_jwt, jwt_superuser, neo4j_graph, site, transactional_db
):
    """A signed-in caller gets 200 and a row per access.

    The plainest thing this endpoint can be asked, and the one nothing checked:
    a 401 here is what emptied the history section on every containerised
    deployment while the graph-level tests stayed green.
    """
    target = await _seed_user(role="staff")

    with patch_jwt(jwt_superuser):
        response = await versioned_client.get(
            f"/api/v2/users/{target.uid}/access-history"
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1, f"expected the user's one access, got {body}"
    assert body[0]["role"] == "staff"
    assert body[0]["active"] is True


async def test_a_role_change_is_visible_through_the_endpoint(
    versioned_client, patch_jwt, jwt_superuser, neo4j_graph, site, transactional_db
):
    """After a change, the route returns both roles with the audit fields.

    This is the user-visible promise of the history section, asserted where the
    page actually reads it. `test_the_previous_access_survives` checks the same
    supersession one layer down; the point of repeating it here is that the
    rows survive serialisation and reach an HTTP caller.
    """
    target = await _seed_user(role="staff")

    # Bracket the change, so the recorded times can be checked against when it
    # actually happened rather than merely for being present. Milliseconds
    # throughout, matching the neomodels' createdAt.
    before = time.time_ns() // 1_000_000

    with patch_jwt(jwt_superuser):
        change = await versioned_client.patch(
            f"/api/v2/users/{target.uid}/role", json={"role": "administrator"}
        )
        assert change.status_code == 200, change.text

        response = await versioned_client.get(
            f"/api/v2/users/{target.uid}/access-history"
        )

    after = time.time_ns() // 1_000_000

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 2, f"expected the old access to survive, got {body}"

    old = next(row for row in body if row["role"] == "staff")
    assert old["active"] is False
    assert old["supersededAt"], "the superseded access records no end time"

    # The former role ended *when the change was made*. A truthy timestamp only
    # says something was written; an audit trail that cannot say when a
    # privilege ended is not one, and a stale or seeded value would satisfy a
    # mere existence check.
    assert before <= old["supersededAt"] <= after, (
        f"the old access ended at {old['supersededAt']}, outside the change "
        f"window {before}–{after}"
    )

    # The seeded access was created long before this test ran, so its end time
    # has to be later than its start — the pair is what makes the row a period
    # rather than two unrelated stamps.
    assert old["supersededAt"] > old["createdAt"]

    # Recorded at the time rather than resolved on read, and carried all the
    # way out to the caller: the page shows who acted, and it has to be the
    # role they held then.
    new = next(row for row in body if row["role"] == "administrator")
    assert new["active"] is True
    assert new["createdByRole"] == "superuser"
    assert new["createdByName"], "the new access records no actor name"


async def test_an_anonymous_caller_is_refused(
    versioned_client, neo4j_graph, site, transactional_db
):
    """No session, no history.

    The trail says who changed whose privileges and when, which is not public.
    Asserted as its own case because the bug this file exists for was a 401
    nobody noticed — a test that only ever asks as a signed-in caller cannot
    tell a working endpoint from one that refuses everybody.
    """
    target = await _seed_user(role="staff")

    response = await versioned_client.get(
        f"/api/v2/users/{target.uid}/access-history"
    )

    assert response.status_code == 401, response.text


async def test_the_history_is_scoped_to_the_site(
    versioned_client, patch_jwt, jwt_superuser, neo4j_graph, site, transactional_db
):
    """Another site's accesses do not appear in this site's history.

    The same person can be staff on one site and an administrator on another,
    and the Entry is what keeps them apart. A history that ignored it would
    leak one site's audit trail into another's page.
    """
    target = await _seed_user(role="staff")

    # The same user, granted a role on a site this request is not about.
    from neomodel import adb

    await adb.cypher_query(
        """
        MATCH (u:User {uid: $user_uid})
        MATCH (e:Entry {uid: $other_entry_uid})
        CREATE (ac:Access {
            uid: $access_uid, role: 'superuser', active: true, createdAt: $now
        })
        CREATE (u)-[:HAS_ACCESS]->(ac)
        CREATE (ac)-[:ACCESS_TO]->(e)
        """,
        {
            "user_uid": target.uid,
            "other_entry_uid": OTHER_ENTRY_UID,
            "access_uid": uuid.uuid4().hex,
            "now": 1_600_000_000_000,
        },
    )

    with patch_jwt(jwt_superuser):
        response = await versioned_client.get(
            f"/api/v2/users/{target.uid}/access-history"
        )

    assert response.status_code == 200, response.text
    body = response.json()
    roles = [row["role"] for row in body]
    assert roles == ["staff"], f"another site's access leaked in: {body}"
