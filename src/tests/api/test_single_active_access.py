"""A user holds at most one active Access per site, and the database enforces it.

Access nodes are the role history: a role change deactivates the current node
and creates another, so a user has many Access nodes per site but only one
active. Neo4j 4.4 cannot constrain "one active per user and site" across
relationships, so the active node carries activeKey = "<user uid>:<entry uid>",
unique by constraint, and a superseded node loses it. The present is
constrained; the history is not.

Every path that activates an Access must set the key — a writer that forgot it
would slip past the constraint unseen, which is why each one is checked here.
Sign-in requests arrive several at a time (the server render and the browser
both ask who the user is), so the first sign-in is checked under concurrency.
"""
import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from asgiref.sync import sync_to_async
from django.core.management import call_command
from neomodel import db
from neomodel.exceptions import ConstraintValidationFailed

from access import access_graph
from access.active_access import enforce_single_active_access, install_constraint
from api import neo4j_auth

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

ENTRY_UID = "e" * 32
EMAIL = "invitee@example.com"
GOOGLE = "https://accounts.google.com"


@pytest_asyncio.fixture
async def graph(neo4j_graph):
    from access.neomodels import Account, User

    install_constraint()
    db.install_labels(User)
    db.install_labels(Account)
    await neo4j_graph.cypher_query(
        "CREATE (:Entry {uid: $uid})", {"uid": ENTRY_UID}
    )
    return neo4j_graph


async def _user(adb, uid=None, sub=None):
    uid = uid or uuid.uuid4().hex
    await adb.cypher_query(
        """
        CREATE (u:User {uid: $uid, email: $email})
        FOREACH (_ IN CASE WHEN $sub IS NULL THEN [] ELSE [1] END |
            CREATE (u)-[:HAS_ACCOUNT]->(:Account {uid: $uid, sub: $sub}))
        """,
        {"uid": uid, "email": f"{uid}@example.com", "sub": sub},
    )
    return uid


async def _invitee(adb, email=EMAIL, role="staff"):
    uid = uuid.uuid4().hex
    await adb.cypher_query(
        """
        MATCH (e:Entry {uid: $entry_uid})
        CREATE (i:Invitee {uid: $uid, email: $email, role: $role, active: true})
        CREATE (i)-[:INVITED_TO]->(e)
        """,
        {"uid": uid, "email": email, "role": role, "entry_uid": ENTRY_UID},
    )
    return SimpleNamespace(uid=uid)


async def _legacy_access(adb, user_uid, role, created_at, active=True,
                         suspended_at=None):
    """An Access as the graph held them before the key existed.

    createdAt is set after the node exists: where the APOC timestamp triggers
    are installed, as in production, creation overwrites it with the clock.
    """
    uid = uuid.uuid4().hex
    await adb.cypher_query(
        """
        MATCH (u:User {uid: $user_uid}), (e:Entry {uid: $entry_uid})
        CREATE (u)-[:HAS_ACCESS]->(:Access {uid: $uid, role: $role,
                active: $active, suspendedAt: $suspended_at})-[:ACCESS_TO]->(e)
        """,
        {"user_uid": user_uid, "entry_uid": ENTRY_UID, "uid": uid,
         "role": role, "active": active, "suspended_at": suspended_at},
    )
    await adb.cypher_query(
        "MATCH (ac:Access {uid: $uid}) SET ac.createdAt = $created_at",
        {"uid": uid, "created_at": created_at},
    )


async def _accesses(adb, user_uid):
    rows, _ = await adb.cypher_query(
        """
        MATCH (:User {uid: $user_uid})-[:HAS_ACCESS]->(ac:Access)
              -[:ACCESS_TO]->(:Entry {uid: $entry_uid})
        RETURN ac.active, ac.activeKey, ac.role
        ORDER BY ac.createdAt
        """,
        {"user_uid": user_uid, "entry_uid": ENTRY_UID},
    )
    return rows


def _key(user_uid):
    return f"{user_uid}:{ENTRY_UID}"


async def test_a_second_active_access_for_the_same_user_and_site_is_refused(graph):
    user_uid = await _user(graph)
    await access_graph.supersede_access(user_uid, ENTRY_UID, "staff", None, "superuser")

    with pytest.raises(ConstraintValidationFailed):
        await graph.cypher_query(
            """
            MATCH (u:User {uid: $user_uid}), (e:Entry {uid: $entry_uid})
            CREATE (u)-[:HAS_ACCESS]->(:Access {uid: $uid, role: 'staff',
                    active: true, activeKey: $key})-[:ACCESS_TO]->(e)
            """,
            {"user_uid": user_uid, "entry_uid": ENTRY_UID,
             "uid": uuid.uuid4().hex, "key": _key(user_uid)},
        )


async def test_the_history_is_not_constrained(graph):
    user_uid = await _user(graph)
    for role in ("staff", "administrator", "staff"):
        await access_graph.supersede_access(user_uid, ENTRY_UID, role, None, "superuser")

    assert await _accesses(graph, user_uid) == [
        [False, None, "staff"],
        [False, None, "administrator"],
        [True, _key(user_uid), "staff"],
    ]


# --- Every writer ------------------------------------------------------------

async def _via_create_user_from_invitee(adb):
    invitee = await _invitee(adb)
    user, _ = await neo4j_auth._create_user_from_invitee(
        invitee, "sub-new", GOOGLE, EMAIL, "New", ENTRY_UID
    )
    return user["uid"]


async def _via_add_access_to_existing_user(adb):
    user_uid = await _user(adb)
    invitee = await _invitee(adb, email=f"{user_uid}@example.com")
    await neo4j_auth._add_access_to_existing_user(
        {"uid": user_uid}, invitee, SimpleNamespace(uid=ENTRY_UID)
    )
    return user_uid


async def _via_ensure_sandbox_access(adb):
    user_uid = await _user(adb)
    await neo4j_auth._ensure_sandbox_access(user_uid, ENTRY_UID)
    return user_uid


async def _via_create_sandbox_user(adb):
    user, _ = await neo4j_auth._create_sandbox_user(
        "sub-sandbox", GOOGLE, "sandbox@example.com", "Sandbox", ENTRY_UID,
    )
    return user["uid"]


async def _via_supersede_access(adb):
    user_uid = await _user(adb)
    await access_graph.supersede_access(user_uid, ENTRY_UID, "staff", None, "superuser")
    return user_uid


async def _via_create_access_command(adb):
    user_uid = await _user(adb)
    creator_uid = await _user(adb)
    await sync_to_async(call_command)(
        "create_access", user=user_uid, entry=ENTRY_UID, role="staff",
        creator=creator_uid,
    )
    return user_uid


@pytest.mark.parametrize("activate", [
    _via_create_user_from_invitee,
    _via_add_access_to_existing_user,
    _via_ensure_sandbox_access,
    _via_create_sandbox_user,
    _via_supersede_access,
    _via_create_access_command,
])
async def test_every_writer_keys_the_access_it_activates(graph, activate):
    user_uid = await activate(graph)

    assert await _accesses(graph, user_uid) == [[True, _key(user_uid), "staff"]]


async def test_the_command_does_not_grant_a_second_role(graph):
    user_uid = await _user(graph)
    creator_uid = await _user(graph)
    await access_graph.supersede_access(user_uid, ENTRY_UID, "staff", None, "superuser")

    await sync_to_async(call_command)(
        "create_access", user=user_uid, entry=ENTRY_UID, role="administrator",
        creator=creator_uid,
    )

    assert await _accesses(graph, user_uid) == [[True, _key(user_uid), "staff"]]


async def test_redeeming_an_invitation_keeps_a_members_current_role(graph):
    """Signing in with a second account under the same address reaches the
    invitation path for a user who already belongs to the site. The role they
    hold stays: changing it is a deliberate act with its own rules."""
    user_uid = await _user(graph, sub="sub-first")
    await access_graph.supersede_access(
        user_uid, ENTRY_UID, "administrator", None, "superuser"
    )
    invitee = await _invitee(graph, email=f"{user_uid}@example.com")

    _, role = await neo4j_auth._create_user_from_invitee(
        invitee, "sub-second", GOOGLE, f"{user_uid}@example.com", "Again",
        ENTRY_UID,
    )

    assert role == "administrator"
    assert await _accesses(graph, user_uid) == [
        [True, _key(user_uid), "administrator"]
    ]


# --- Simultaneous first sign-ins ---------------------------------------------

async def _sign_in_eight_times(jwt, sandbox):
    with patch.object(neo4j_auth, "_get_entry_uid", AsyncMock(return_value=ENTRY_UID)), \
         patch.object(neo4j_auth, "_is_sandbox", AsyncMock(return_value=sandbox)):
        return await asyncio.gather(
            *(neo4j_auth.get_or_create_neo4j_user(jwt, site=None) for _ in range(8))
        )


async def test_simultaneous_first_sign_ins_with_an_invitation(graph):
    await _invitee(graph)
    jwt = {"providerAccountId": "sub-racer", "iss": GOOGLE, "email": EMAIL,
           "name": "Racer"}

    responses = await _sign_in_eight_times(jwt, sandbox=False)

    assert [r and r["role"] for r in responses] == ["staff"] * 8
    user_uid = responses[0]["uid"]
    assert await _accesses(graph, user_uid) == [[True, _key(user_uid), "staff"]]


async def test_a_sign_in_overtaken_by_a_concurrent_one_still_gets_its_role(graph):
    """Between looking the user up and looking for their invitation, another
    request of the same sign-in can create the user and redeem it. The late
    request then finds neither, and must look again rather than refuse."""
    invitee = await _invitee(graph)
    await neo4j_auth._create_user_from_invitee(
        invitee, "sub-racer", GOOGLE, EMAIL, "Racer", ENTRY_UID
    )
    find_user_by_sub = neo4j_auth._find_user_by_sub
    lookups = []

    async def overtaken(sub, entry_uid):
        lookups.append(sub)
        return None if len(lookups) == 1 else await find_user_by_sub(sub, entry_uid)

    jwt = {"providerAccountId": "sub-racer", "iss": GOOGLE, "email": EMAIL,
           "name": "Racer"}
    with patch.object(neo4j_auth, "_get_entry_uid", AsyncMock(return_value=ENTRY_UID)), \
         patch.object(neo4j_auth, "_is_sandbox", AsyncMock(return_value=False)), \
         patch.object(neo4j_auth, "_find_user_by_sub", overtaken):
        response = await neo4j_auth.get_or_create_neo4j_user(jwt, site=None)

    assert response and response["role"] == "staff"


async def test_simultaneous_first_sign_ins_on_a_sandbox(graph):
    jwt = {"providerAccountId": "sub-sandbox-racer", "iss": GOOGLE,
           "email": "sandbox-racer@example.com", "name": "Racer"}

    responses = await _sign_in_eight_times(jwt, sandbox=True)

    assert [r and r["role"] for r in responses] == ["staff"] * 8
    user_uid = responses[0]["uid"]
    assert await _accesses(graph, user_uid) == [[True, _key(user_uid), "staff"]]


# --- Repairing the graph as it was -------------------------------------------

async def test_identical_duplicates_are_deleted_keeping_the_original(graph):
    user_uid = await _user(graph)
    await _legacy_access(graph, user_uid, "staff", created_at=1_000)
    await _legacy_access(graph, user_uid, "staff", created_at=1_016)

    enforce_single_active_access()

    rows, _ = await graph.cypher_query(
        "MATCH (:User {uid: $u})-[:HAS_ACCESS]->(ac:Access) RETURN ac.createdAt",
        {"u": user_uid},
    )
    assert rows == [[1_000]]
    assert await _accesses(graph, user_uid) == [[True, _key(user_uid), "staff"]]


async def test_different_roles_keep_the_most_recent_and_end_the_older(graph):
    user_uid = await _user(graph)
    await _legacy_access(graph, user_uid, "staff", created_at=1_000)
    await _legacy_access(graph, user_uid, "superuser", created_at=2_000)

    enforce_single_active_access()

    rows, _ = await graph.cypher_query(
        """
        MATCH (:User {uid: $u})-[:HAS_ACCESS]->(ac:Access)
        RETURN ac.role, ac.active, ac.activeKey, ac.supersededAt
        ORDER BY ac.createdAt
        """,
        {"u": user_uid},
    )
    assert rows == [
        ["staff", False, None, 2_000],
        ["superuser", True, _key(user_uid), None],
    ]


async def test_the_repair_leaves_the_history_alone(graph):
    user_uid = await _user(graph)
    await _legacy_access(graph, user_uid, "staff", created_at=500, active=False)
    await _legacy_access(graph, user_uid, "administrator", created_at=1_000)

    enforce_single_active_access()

    assert await _accesses(graph, user_uid) == [
        [False, None, "staff"],
        [True, _key(user_uid), "administrator"],
    ]


async def test_the_repair_never_lifts_a_suspension(graph):
    user_uid = await _user(graph)
    await _legacy_access(graph, user_uid, "staff", created_at=1_000)
    await _legacy_access(graph, user_uid, "staff", created_at=1_016,
                         suspended_at=5_000)

    enforce_single_active_access()

    rows, _ = await graph.cypher_query(
        """
        MATCH (:User {uid: $u})-[:HAS_ACCESS]->(ac:Access {active: true})
        RETURN ac.suspendedAt
        """,
        {"u": user_uid},
    )
    assert rows == [[5_000]]


async def test_the_repair_deletes_pending_invitations_held_by_members(graph):
    member_uid = await _user(graph)
    await _legacy_access(graph, member_uid, "staff", created_at=1_000)
    await _invitee(graph, email=f"{member_uid}@example.com")
    await _invitee(graph, email="newcomer@example.com")

    enforce_single_active_access()

    rows, _ = await graph.cypher_query("MATCH (i:Invitee) RETURN i.email")
    assert rows == [["newcomer@example.com"]]


async def test_the_repair_can_run_again(graph):
    user_uid = await _user(graph)
    await _legacy_access(graph, user_uid, "staff", created_at=1_000)

    first = enforce_single_active_access()
    second = enforce_single_active_access()

    assert first == second == {
        "deleted": 0, "retired": 0, "keyed": 1, "invitations_deleted": 0,
    }
