"""POST /api/v2/invitees/{uid}/resend: send an invitation's email again.

The same rights as creating one (invitees_v2), for an invitation of this
site's organization only. A new EmailDelivery row is recorded, so a failure
stays in the history; the answer is the invitation with its new, queued
emailDelivery. Refused with 409 and a code the page translates when the
invitation is used or deactivated, or its previous email is still on its
way (mailer.delivery.resend_refusal).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.utils import timezone
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio

UID = "a" * 32
URL = f"/api/v2/invitees/{UID}/resend"


def _node(**fields):
    props = {"uid": UID, "email": "who@example.org", "name": "Who", "role": "staff", "active": True, "redeemedAt": None}
    props.update(fields)
    return SimpleNamespace(__properties__=props, **props)


@pytest.fixture
def resend():
    from main import app
    from api.auth import JWT

    app.dependency_overrides[JWT] = lambda: {"sub": "admin"}
    state = {"node": _node(), "latest": {}}
    queued = SimpleNamespace(status="queued", error="", updated=timezone.now())
    with (
        patch("api.routers.invitees.authorize_api", AsyncMock(return_value=True)) as authorize,
        patch("api.routers.invitees.verify_invitee_ownership", AsyncMock()) as ownership,
        patch("api.routers.invitees.get_site_from_request", AsyncMock(return_value=MagicMock())),
        # `nodes` is built afresh on each access, so its `get` cannot be
        # patched by path; the whole manager is replaced.
        patch(
            "api.routers.invitees.AsyncInvitee.nodes",
            MagicMock(get=AsyncMock(side_effect=lambda uid: state["node"])),
        ),
        patch("api.routers.invitees.latest_deliveries", MagicMock(side_effect=lambda uids: state["latest"])),
        patch("api.routers.invitees.notification_email", AsyncMock()) as send,
        # Remembered addresses are tested in test_bad_addresses.py.
        patch("api.routers.invitees.site_organization", AsyncMock(return_value=None)),
        patch("api.routers.invitees.blocking", MagicMock(return_value=None)),
        patch("api.routers.invitees.issues_for", MagicMock(return_value={})),
    ):
        state.update(authorize=authorize, ownership=ownership, send=send, queued=queued)
        try:
            yield state
        finally:
            app.dependency_overrides.pop(JWT, None)


async def test_the_email_is_sent_again(versioned_client, resend):
    async def sent(invitee, site, force=False):
        resend["latest"] = {UID: resend["queued"]}

    resend["send"].side_effect = sent

    response = await versioned_client.post(URL)

    assert response.status_code == 200
    assert resend["send"].await_args.args[0].email == "who@example.org"
    assert response.json()["emailDelivery"]["status"] == "queued"


async def test_it_takes_the_rights_of_creating_an_invitation(versioned_client, resend):
    await versioned_client.post(URL)

    assert resend["authorize"].await_args.args[0] == "invitees_v2"
    resend["ownership"].assert_awaited_once()


async def test_a_refused_caller_sends_nothing(versioned_client, resend):
    resend["authorize"].side_effect = HTTPException(status_code=403)

    response = await versioned_client.post(URL)

    assert response.status_code == 403
    resend["send"].assert_not_awaited()


async def test_another_organizations_invitation_is_not_sent(versioned_client, resend):
    resend["ownership"].side_effect = HTTPException(status_code=403)

    response = await versioned_client.post(URL)

    assert response.status_code == 403
    resend["send"].assert_not_awaited()


@pytest.mark.parametrize(
    "node, latest, code",
    [
        (_node(redeemedAt=1790000000000), {}, "used"),
        (_node(active=False), {}, "disabled"),
        (_node(), {UID: SimpleNamespace(status="queued", error="", updated=timezone.now())}, "already_queued"),
    ],
    ids=["used", "disabled", "already_queued"],
)
async def test_a_refusal_is_a_409_with_its_code(versioned_client, resend, node, latest, code):
    resend["node"], resend["latest"] = node, latest

    response = await versioned_client.post(URL)

    assert response.status_code == 409
    assert response.json()["detail"] == {"code": code}
    resend["send"].assert_not_awaited()
