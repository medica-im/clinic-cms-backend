"""GET /api/v2/users and /users/{uid}: each user's accounts and accesses.

The query collects a user's Accounts and active Accesses. neomodel 5 handed
each list back wrapped in one more list, which the route unwrapped
(`[account_nodes]`); neomodel 6 hands them back as Cypher built them. Either
way the response must list every account, none for a user who has none.
"""

import uuid

import pytest
import pytest_asyncio
from neomodel import adb

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

ENTRY_UID = uuid.uuid4().hex
TWO_ACCOUNTS, NO_ACCOUNT = uuid.uuid4().hex, uuid.uuid4().hex


@pytest.fixture(autouse=True)
def users_acl(transactional_db, roles):
    from access.models import AccessControl, Endpoint

    endpoint, _ = Endpoint.objects.get_or_create(name="users_v2")
    AccessControl.objects.get_or_create(
        endpoint=endpoint, role=roles["superuser"], defaults={"permissions": 15}
    )


@pytest_asyncio.fixture(autouse=True)
async def organization(neo4j_graph, site, transactional_db):
    from facility.models import Organization

    await adb.cypher_query("CREATE (:Entry {uid: $uid})", {"uid": ENTRY_UID})
    await Organization.objects.acreate(name="Test Org", site=site, neomodel_uid=ENTRY_UID)


async def seed(uid, role, subs):
    await adb.cypher_query(
        """
        MATCH (e:Entry {uid: $entry})
        CREATE (u:User {uid: $uid, email: $uid + '@example.com'})
        CREATE (u)-[:HAS_ACCESS]->(:Access {uid: $uid + '-access', role: $role, active: true})-[:ACCESS_TO]->(e)
        WITH u
        UNWIND $subs AS sub
        CREATE (u)-[:HAS_ACCOUNT]->(:Account {uid: sub + '-account', sub: sub})
        """,
        {"entry": ENTRY_UID, "uid": uid, "role": role, "subs": subs},
    )


@pytest_asyncio.fixture
async def users(organization, jwt_superuser):
    await seed(uuid.uuid4().hex, "superuser", [jwt_superuser["sub"]])
    await seed(TWO_ACCOUNTS, "staff", ["google-sub", "apple-sub"])
    await seed(NO_ACCOUNT, "staff", [])


def accounts(user):
    return sorted(a["sub"] for a in user["accounts"])


def roles_of(user):
    return [ac["role"] for ac in user["access"]]


async def test_the_list_gives_each_user_their_accounts(users, versioned_client, patch_jwt, jwt_superuser):
    with patch_jwt(jwt_superuser):
        response = await versioned_client.get("/api/v2/users")

    assert response.status_code == 200
    by_uid = {u["uid"]: u for u in response.json()}
    assert accounts(by_uid[TWO_ACCOUNTS]) == ["apple-sub", "google-sub"]
    assert roles_of(by_uid[TWO_ACCOUNTS]) == ["staff"]
    assert accounts(by_uid[NO_ACCOUNT]) == []
    assert roles_of(by_uid[NO_ACCOUNT]) == ["staff"]


@pytest.mark.parametrize("uid, subs", [(TWO_ACCOUNTS, ["apple-sub", "google-sub"]), (NO_ACCOUNT, [])])
async def test_one_user_comes_with_their_accounts(users, versioned_client, patch_jwt, jwt_superuser, uid, subs):
    with patch_jwt(jwt_superuser):
        response = await versioned_client.get(f"/api/v2/users/{uid}")

    assert response.status_code == 200
    assert accounts(response.json()) == subs
    assert roles_of(response.json()) == ["staff"]
