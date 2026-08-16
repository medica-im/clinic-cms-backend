"""Who may change whose role, and to what.

The permission matrix, checked as a table rather than as a browser scenario
each. Every row here is a rule from features/user-role-change.feature, which
keeps the prose and the reasoning; this file is where the rules are actually
enforced, because the endpoint has to refuse a request made directly and a
hidden button proves nothing about that.

The rules, and why each exists:

* **Nobody grants a role above their own.** The escalation the whole feature
  exists to prevent — otherwise an administrator promotes themselves by way of
  a second account.
* **An administrator cannot modify another administrator.** Two administrators
  are peers; letting one demote the other turns a disagreement into a race and
  makes every administrator a single point of failure for the rest.
* **Only a superuser, or the user themselves, demotes.** Stepping down is
  always allowed. Pushing somebody else down is not.
* **The last superuser cannot step down.** Otherwise nobody can ever promote
  anyone again, and the way back is the Django shell.
* **A suspended account's role cannot change.** A promotion would arrive as a
  fresh Access with no suspension on it, which is precisely what suspension
  exists to prevent.
* **Only a superuser suspends, and never themselves.** Suspending yourself is
  a confusing logout that leaves nobody able to undo it.

A role is superseded, never overwritten: the change deactivates the current
Access and creates a new one, so the previous role survives with the time it
ended and who ended it. `test_the_previous_access_survives` is that invariant,
and `test_one_active_access_per_site` is the one Neo4j 4.4 cannot express as a
constraint — the same reason the Entry graph model is pinned by test rather
than by the database.
"""
import uuid

import pytest
import pytest_asyncio

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# The Entry every Access on this site hangs from. A role is always a role
# *somewhere*, so the seeding and the endpoint have to agree on which Entry
# they mean; fixing it here keeps the two in step.
ENTRY_UID = uuid.uuid4().hex


@pytest.fixture(autouse=True)
def users_acl(transactional_db, roles):
    """AccessControl rows for users_v2, per the matrix in CLAUDE.md.

    Autouse because without these rows `may_authorize` refuses everybody, and
    the whole permission matrix would pass for the wrong reason — every case
    403 whatever the rules say.
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
    """The site's Organization and its Entry, in both databases.

    The endpoint finds the Entry through the Postgres Organization row, so a
    graph node alone is not enough — without the row every request 404s before
    any rule is reached.
    """
    from facility.models import Organization

    await neo4j_graph.cypher_query(
        "CREATE (e:Entry {uid: $uid})", {"uid": ENTRY_UID}
    )
    await Organization.objects.acreate(
        name="Test Org", site=site, neomodel_uid=ENTRY_UID
    )


class SeededUser:
    """Just enough of a user for a test to name one: `target.uid`."""

    def __init__(self, uid, sub):
        self.uid = uid
        self.sub = sub


@pytest_asyncio.fixture(autouse=True)
async def a_second_superuser(organization):
    """A superuser who is not the caller and not any test's target.

    Every rule about the *last* superuser is a rule about a count, so a site
    with exactly one superuser makes "may a superuser be demoted?" and "is this
    the last one?" the same question — and the tests that mean the first would
    pass on the second. This one is never acted on, so it keeps the count above
    one without taking part.

    Tests about the last superuser seed their caller as the only usable one and
    are written to remove this one from the count.
    """
    return await _seed_user(role="superuser", sub="second-superuser-sub")


@pytest_asyncio.fixture(autouse=True)
async def caller_identities(organization, request):
    """Give each JWT fixture a matching User, Account and Access.

    The endpoint reads what a caller may do from their Access, so a test that
    only patches a JWT is making a request as somebody the graph has never
    heard of — judged anonymous, refused, and green for the wrong reason. Tests
    that seed their own caller (to make them the target, or to suspend them)
    take precedence: those run after this fixture and supersede what it made.
    """
    seeded = {}
    for role in ("superuser", "administrator", "staff", "registered"):
        jwt = request.getfixturevalue(f"jwt_{role}")
        seeded[role] = await _seed_user(role=role, sub=jwt["sub"])
    return seeded


async def _seed_user(role, sub=None, suspended=False):
    """Create a User with an Account and one active Access for this site.

    `sub` ties the user to a JWT fixture, which is how a test says "this is the
    caller" — the endpoint resolves the actor by Account sub, so a user seeded
    without a matching sub is somebody else.
    """
    from neomodel import adb

    user_uid = uuid.uuid4().hex
    sub = sub or f"sub-{user_uid}"
    now = 1_600_000_000_000

    # Seeding the same sub twice replaces rather than duplicates: a test that
    # seeds its own caller — to make them the target, or to suspend them — is
    # restating who that person is, and two Accounts with one sub would make
    # the endpoint's lookup pick one arbitrarily.
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
            uid: $access_uid, role: $role, active: true, createdAt: $now,
            suspendedAt: $suspended_at
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
            "name": f"User {user_uid[:8]}",
            "role": role,
            "now": now,
            "suspended_at": now if suspended else None,
        },
    )
    return SeededUser(user_uid, sub)


async def _demote_other_superusers(keep):
    """Leave `keep` as the site's only usable superuser.

    Demotes rather than deletes, so the other accounts still exist and the
    difference between "no other superuser" and "no other user" cannot be what
    makes a test pass.
    """
    from neomodel import adb

    await adb.cypher_query(
        """
        MATCH (u:User)-[:HAS_ACCESS]->(ac:Access {active: true, role: 'superuser'})
              -[:ACCESS_TO]->(e:Entry {uid: $entry_uid})
        WHERE u.uid <> $keep
        SET ac.role = 'administrator'
        """,
        {"entry_uid": ENTRY_UID, "keep": keep},
    )


async def _current_role(user_uid):
    """The role on the user's active access, or None."""
    from access import access_graph

    access = await access_graph.get_access(user_uid, ENTRY_UID)
    return access["role"] if access else None


async def _access_history(user_uid):
    """Every access the user has held here, current and superseded."""
    from access import access_graph

    return await access_graph.access_history(user_uid, ENTRY_UID)


# actor role, target's current role, role asked for, expected status.
#
# 403 is "you may not do this"; 409 is "this cannot be done" — the last
# superuser and the suspended account are refused whoever asks, so they are
# conflicts rather than permission failures, per the project's split between
# AccessControl and the serializer layer.
MATRIX = [
    # An administrator works below their own level, and only upwards.
    ("administrator", "staff", "administrator", 200),
    ("administrator", "registered", "staff", 200),
    ("administrator", "staff", "superuser", 403),
    # ... and never on a peer, in either direction.
    ("administrator", "administrator", "staff", 403),
    ("administrator", "administrator", "superuser", 403),
    ("administrator", "superuser", "staff", 403),
    # A superuser may grant anything to anyone.
    ("superuser", "staff", "superuser", 200),
    ("superuser", "administrator", "staff", 200),
    ("superuser", "superuser", "administrator", 200),
    # Nobody below administrator may grant at all.
    ("staff", "registered", "staff", 403),
    ("registered", "registered", "staff", 403),
    ("anonymous", "staff", "administrator", 403),
]


@pytest.mark.parametrize("actor,target_role,granted,expected", MATRIX)
async def test_who_may_grant_what(
    versioned_client, patch_jwt, request, neo4j_graph, site, transactional_db,
    actor, target_role, granted, expected
):
    """One case per rule. A failure names the row that broke."""
    jwt = None if actor == "anonymous" else request.getfixturevalue(f"jwt_{actor}")
    target = await _seed_user(role=target_role)

    with patch_jwt(jwt):
        response = await versioned_client.patch(
            f"/api/v2/users/{target.uid}/role", json={"role": granted}
        )

    assert response.status_code == expected, (
        f"{actor} granting {granted!r} to a {target_role} user "
        f"-> {response.status_code}, expected {expected}: {response.text[:200]}"
    )


async def test_a_user_may_step_down(versioned_client, patch_jwt, jwt_administrator, neo4j_graph, site, transactional_db):
    """Stepping down is always allowed, whatever the rules say about others."""
    me = await _seed_user(role="administrator", sub=jwt_administrator["sub"])

    with patch_jwt(jwt_administrator):
        response = await versioned_client.patch(
            f"/api/v2/users/{me.uid}/role", json={"role": "staff"}
        )

    assert response.status_code == 200, response.text
    assert await _current_role(me.uid) == "staff"


async def test_the_last_superuser_cannot_step_down(
    versioned_client, patch_jwt, jwt_superuser, neo4j_graph, site, transactional_db
):
    me = await _seed_user(role="superuser", sub=jwt_superuser["sub"])
    # The rule is about a count, so the caller has to actually be the last one:
    # with anybody else still able to promote, stepping down is allowed and
    # this test would be asserting the opposite rule.
    await _demote_other_superusers(keep=me.uid)

    with patch_jwt(jwt_superuser):
        response = await versioned_client.patch(
            f"/api/v2/users/{me.uid}/role", json={"role": "administrator"}
        )

    assert response.status_code == 409, response.text
    assert await _current_role(me.uid) == "superuser"


async def test_a_suspended_users_role_cannot_change(
    versioned_client, patch_jwt, jwt_superuser, neo4j_graph, site, transactional_db
):
    target = await _seed_user(role="staff", suspended=True)

    with patch_jwt(jwt_superuser):
        response = await versioned_client.patch(
            f"/api/v2/users/{target.uid}/role", json={"role": "administrator"}
        )

    assert response.status_code == 409, response.text
    assert await _current_role(target.uid) == "staff"


async def test_a_suspended_caller_has_no_privileges(
    versioned_client, patch_jwt, jwt_administrator, neo4j_graph, site, transactional_db
):
    """The suspension applies to the actor, not only to the target."""
    await _seed_user(role="administrator", sub=jwt_administrator["sub"], suspended=True)
    target = await _seed_user(role="staff")

    with patch_jwt(jwt_administrator):
        response = await versioned_client.patch(
            f"/api/v2/users/{target.uid}/role", json={"role": "administrator"}
        )

    assert response.status_code == 403, response.text


# --- Suspension --------------------------------------------------------------

SUSPEND_MATRIX = [
    ("superuser", "administrator", 200),
    ("superuser", "staff", 200),
    ("administrator", "staff", 403),
    ("staff", "registered", 403),
]


@pytest.mark.parametrize("actor,target_role,expected", SUSPEND_MATRIX)
async def test_who_may_suspend(
    versioned_client, patch_jwt, request, neo4j_graph, site, transactional_db,
    actor, target_role, expected
):
    jwt = request.getfixturevalue(f"jwt_{actor}")
    target = await _seed_user(role=target_role)

    with patch_jwt(jwt):
        response = await versioned_client.post(
            f"/api/v2/users/{target.uid}/suspension",
            json={"reason": "incident"},
        )

    assert response.status_code == expected, (
        f"{actor} suspending a {target_role} user -> {response.status_code}, "
        f"expected {expected}: {response.text[:200]}"
    )


async def test_a_superuser_cannot_suspend_themselves(
    versioned_client, patch_jwt, jwt_superuser, neo4j_graph, site, transactional_db
):
    me = await _seed_user(role="superuser", sub=jwt_superuser["sub"])

    with patch_jwt(jwt_superuser):
        response = await versioned_client.post(
            f"/api/v2/users/{me.uid}/suspension", json={"reason": "oops"}
        )

    assert response.status_code == 409, response.text


async def test_restoring_lets_the_role_change_again(
    versioned_client, patch_jwt, jwt_superuser, neo4j_graph, site, transactional_db
):
    target = await _seed_user(role="staff", suspended=True)

    with patch_jwt(jwt_superuser):
        restored = await versioned_client.delete(f"/api/v2/users/{target.uid}/suspension")
        assert restored.status_code == 200, restored.text

        changed = await versioned_client.patch(
            f"/api/v2/users/{target.uid}/role", json={"role": "administrator"}
        )

    assert changed.status_code == 200, changed.text
    assert await _current_role(target.uid) == "administrator"


# --- The audit trail ---------------------------------------------------------

async def test_the_previous_access_survives(
    versioned_client, patch_jwt, jwt_superuser, neo4j_graph, site, transactional_db
):
    """A role change supersedes; it does not overwrite.

    This is what makes the history section possible at all: the old Access is
    still there, marked inactive, with when it ended and who ended it.
    """
    target = await _seed_user(role="staff")

    with patch_jwt(jwt_superuser):
        response = await versioned_client.patch(
            f"/api/v2/users/{target.uid}/role", json={"role": "administrator"}
        )
    assert response.status_code == 200, response.text

    history = await _access_history(target.uid)
    assert len(history) == 2, f"expected the old access to survive, got {history}"

    old = next(a for a in history if a["role"] == "staff")
    assert old["active"] is False
    assert old["supersededAt"], "the superseded access records no end time"
    assert old["supersededBy"], "the superseded access records no actor"

    # Recorded at the time, not resolved on read: an actor demoted tomorrow
    # still acted as a superuser today.
    new = next(a for a in history if a["role"] == "administrator")
    assert new["createdByRole"] == "superuser"


async def test_one_active_access_per_site(
    versioned_client, patch_jwt, jwt_superuser, neo4j_graph, site, transactional_db
):
    """At most one active Access per user per site.

    Neo4j 4.4 cannot express this as a constraint, so it is pinned here — the
    same reason the Entry graph model is a test rather than a schema rule. Two
    active accesses would make "the user's role" ambiguous, and which one wins
    would depend on traversal order.
    """
    target = await _seed_user(role="staff")

    with patch_jwt(jwt_superuser):
        for role in ("administrator", "superuser", "staff"):
            response = await versioned_client.patch(
                f"/api/v2/users/{target.uid}/role", json={"role": role}
            )
            assert response.status_code == 200, response.text

    history = await _access_history(target.uid)
    active = [a for a in history if a["active"]]
    assert len(active) == 1, f"expected exactly one active access, got {active}"
    assert active[0]["role"] == "staff"
