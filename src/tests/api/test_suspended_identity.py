"""A suspended user is told, rather than left guessing.

Suspension withholds privileges without ending the identity: signing in still
works, and the account keeps its role so a suspended administrator stays
distinguishable from an ordinary user. That is deliberate — the alternative, a
silent downgrade to `registered`, leaves the dashboard nothing to explain and
the person looking at a site that has quietly stopped working.

For the page to say anything, `/users/me` has to carry the fact. Without it a
suspended user and a user with no access at all arrive identically (`role:
null`), and the only honest thing the dashboard could print is nothing.

The rules themselves live in tests/api/test_role_change.py; this file is only
about what the suspended person is told.
"""
import uuid

import pytest
import pytest_asyncio

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


ENTRY_UID = uuid.uuid4().hex


@pytest_asyncio.fixture(autouse=True)
async def organization(neo4j_graph, site, transactional_db):
    from facility.models import Organization

    await neo4j_graph.cypher_query(
        "CREATE (e:Entry {uid: $uid})", {"uid": ENTRY_UID}
    )
    await Organization.objects.acreate(
        name="Test Org", site=site, neomodel_uid=ENTRY_UID
    )


async def _seed(role, sub, suspended=False, reason=None):
    from neomodel import adb

    user_uid = uuid.uuid4().hex
    now = 1_600_000_000_000
    await adb.cypher_query(
        """
        MATCH (e:Entry {uid: $entry_uid})
        CREATE (u:User {uid: $user_uid, email: $email, name: 'Test', createdAt: $now})
        CREATE (a:Account {uid: $account_uid, sub: $sub, createdAt: $now})
        CREATE (u)-[:HAS_ACCOUNT]->(a)
        CREATE (ac:Access {
            uid: $access_uid, role: $role, active: true, createdAt: $now,
            suspendedAt: $suspended_at, suspensionReason: $reason
        })
        CREATE (u)-[:HAS_ACCESS]->(ac)
        CREATE (ac)-[:ACCESS_TO]->(e)
        """,
        {
            "entry_uid": ENTRY_UID,
            "user_uid": user_uid,
            "account_uid": uuid.uuid4().hex,
            "access_uid": uuid.uuid4().hex,
            "sub": sub,
            "email": f"{user_uid}@example.com",
            "role": role,
            "now": now,
            "suspended_at": now if suspended else None,
            "reason": reason,
        },
    )
    return user_uid


async def test_a_suspended_user_is_told_they_are_suspended(
    versioned_client, patch_jwt, jwt_administrator, neo4j_graph, site, transactional_db
):
    """The dashboard needs a reason to show a notice, and this is it."""
    await _seed("administrator", jwt_administrator["sub"], suspended=True,
                reason="incident")

    with patch_jwt(jwt_administrator):
        response = await versioned_client.get("/api/v2/users/me")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["suspended"] is True
    assert body["suspensionReason"] == "incident"


async def test_a_suspended_user_holds_no_role(
    versioned_client, patch_jwt, jwt_administrator, neo4j_graph, site, transactional_db
):
    """The identity survives; the privileges do not.

    If the role came back, every authorization decision downstream would grant
    it — the suspension would be a label on a page and nothing more.
    """
    await _seed("administrator", jwt_administrator["sub"], suspended=True)

    with patch_jwt(jwt_administrator):
        response = await versioned_client.get("/api/v2/users/me")

    assert response.json()["role"] is None


async def test_an_ordinary_user_is_not_marked_suspended(
    versioned_client, patch_jwt, jwt_staff, neo4j_graph, site, transactional_db
):
    """The flag has to distinguish, or the dashboard warns everybody."""
    await _seed("staff", jwt_staff["sub"])

    with patch_jwt(jwt_staff):
        response = await versioned_client.get("/api/v2/users/me")

    body = response.json()
    assert body["suspended"] is False
    assert body["role"] == "staff"
