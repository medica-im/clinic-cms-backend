"""Nobody is invited to a site they already belong to.

An invitation exists to give someone a role. A member already has one, and
changing it is a deliberate act on the user page with its own rules (the last
superuser, suspension, who may grant what); an invitation would be a way round
them. A suspended member is still a member: what they need is the suspension
lifted, not a second way in.

Membership is an active Access on the site's Entry, matched on the address
regardless of case, as sign-in matches it.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async

from access import access_graph

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

ENTRY_UID = uuid.uuid4().hex
OTHER_ENTRY_UID = uuid.uuid4().hex
MEMBER_EMAIL = "member@example.com"


@pytest.fixture
async def graph(neo4j_graph):
    await neo4j_graph.cypher_query(
        "CREATE (:Entry {uid: $a}), (:Entry {uid: $b})",
        {"a": ENTRY_UID, "b": OTHER_ENTRY_UID},
    )
    return neo4j_graph


async def _member(adb, entry_uid=ENTRY_UID, email=MEMBER_EMAIL):
    user_uid = uuid.uuid4().hex
    await adb.cypher_query(
        "CREATE (:User {uid: $uid, email: $email})",
        {"uid": user_uid, "email": email},
    )
    await access_graph.supersede_access(user_uid, entry_uid, "staff", None, "superuser")


async def _invitees(adb):
    rows, _ = await adb.cypher_query("MATCH (i:Invitee) RETURN toLower(i.email)")
    return sorted(r[0] for r in rows)


def _site_of(entry_uid):
    organization = SimpleNamespace(neomodel_uid=uuid.UUID(entry_uid))
    return (
        patch("api.routers.invitees.authorize_api", AsyncMock(return_value=True)),
        patch("api.routers.invitees.get_site_from_request",
              AsyncMock(return_value=MagicMock())),
        patch("api.routers.invitees.Organization.objects.aget",
              AsyncMock(return_value=organization)),
    )


async def _invite(client, patch_jwt, jwt, email, entry_uid=ENTRY_UID):
    auth, site, organization = _site_of(entry_uid)
    with patch_jwt(jwt), auth, site, organization:
        return await client.post("/api/v2/invitees", json={
            "email": email, "role": "staff", "name": "Someone",
            "entry": entry_uid, "createdBy": "x",
        })


@pytest.mark.parametrize("address", [MEMBER_EMAIL, "Member@Example.COM"])
async def test_a_member_is_not_invited_again(
    versioned_client, patch_jwt, jwt_administrator, graph, address
):
    await _member(graph)

    response = await _invite(versioned_client, patch_jwt, jwt_administrator, address)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ALREADY_MEMBER"
    assert await _invitees(graph) == []


async def test_a_member_of_another_site_may_be_invited_here(graph):
    from access.active_access import is_member

    await _member(graph, entry_uid=OTHER_ENTRY_UID)

    assert not await is_member(MEMBER_EMAIL, ENTRY_UID)
    assert await is_member(MEMBER_EMAIL, OTHER_ENTRY_UID)


async def test_the_batch_skips_members_and_invites_the_others(graph):
    from access.models import BatchInviteeJob
    from access.tasks import process_batch_invitees

    await _member(graph)
    job = await BatchInviteeJob.objects.acreate(
        organization_neomodel_uid=uuid.UUID(ENTRY_UID), user_uid="x",
        total_rows=2, role="staff", send_emails=False,
    )

    await sync_to_async(process_batch_invitees)(
        job.id,
        [{"email": "MEMBER@example.com", "name": ""},
         {"email": "newcomer@example.com", "name": ""}],
        ENTRY_UID, "no-such-sub", "staff", False, "testserver",
    )

    await job.arefresh_from_db()
    assert [row["status"] for row in job.summary] == ["skipped_active_user", "created"]
    assert job.skipped_active_user_count == 1
    assert await _invitees(graph) == ["newcomer@example.com"]
