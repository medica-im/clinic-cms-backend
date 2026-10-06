"""The invitations API says whether each invitation's email went out.

emailDelivery on every invitation: the latest attempt's status (queued,
sent, failed -- including a queued email nobody settled, marked timedOut), when it
last changed, and the reason of a failure. null for an invitation with no
recorded attempt -- one created before recording began, or with no email.
How attempts are recorded is tested in tests/test_email_delivery.py.
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.utils import timezone

pytestmark = pytest.mark.asyncio

SENT_UID = "a" * 32
FAILED_UID = "b" * 32
UNKNOWN_UID = "c" * 32


def _node(uid, email):
    return {"uid": uid, "email": email, "name": None, "role": "staff", "active": True, "createdAt": 1790000000000}


def _row(status, error="", age=timedelta(0)):
    return SimpleNamespace(status=status, error=error, updated=timezone.now() - age)


@pytest.fixture
def listed():
    """An organization with three invitations, and deliveries for two."""
    from main import app
    from api.auth import JWT

    app.dependency_overrides[JWT] = lambda: {"sub": "admin"}
    rows = [
        [_node(SENT_UID, "sent@example.org"), None],
        [_node(FAILED_UID, "failed@example.org"), None],
        [_node(UNKNOWN_UID, "old@example.org"), None],
    ]
    deliveries = {
        SENT_UID: _row("sent"),
        FAILED_UID: _row("failed", error="401: Forbidden"),
    }
    with (
        patch("api.routers.invitees.authorize_api", AsyncMock(return_value=True)),
        patch("api.routers.invitees.get_site_from_request", AsyncMock(return_value=MagicMock())),
        patch(
            "api.routers.invitees.Organization.objects.aget",
            AsyncMock(return_value=MagicMock(neomodel_uid=MagicMock(hex="e" * 32))),
        ),
        patch("api.routers.invitees.adb.cypher_query", AsyncMock(return_value=(rows, None))),
        patch("api.routers.invitees.latest_deliveries", MagicMock(return_value=deliveries)) as lookup,
        # Remembered addresses are tested in test_bad_addresses.py.
        patch("api.routers.invitees.issues_for", MagicMock(return_value={})),
    ):
        try:
            yield lookup
        finally:
            app.dependency_overrides.pop(JWT, None)


async def test_each_invitation_says_whether_its_email_went_out(versioned_client, listed):
    response = await versioned_client.get("/api/v2/invitees")

    by_uid = {i["uid"]: i["emailDelivery"] for i in response.json()}
    assert by_uid[SENT_UID]["status"] == "sent"
    assert by_uid[SENT_UID]["error"] is None
    assert by_uid[FAILED_UID]["status"] == "failed"
    assert by_uid[FAILED_UID]["error"] == "401: Forbidden"
    assert by_uid[FAILED_UID]["timedOut"] is False
    assert by_uid[UNKNOWN_UID] is None


async def test_the_deliveries_are_looked_up_in_one_query(versioned_client, listed):
    await versioned_client.get("/api/v2/invitees")

    listed.assert_called_once()
    assert set(listed.call_args.args[0]) == {SENT_UID, FAILED_UID, UNKNOWN_UID}


async def test_an_email_queued_too_long_is_reported_failed_and_timed_out(versioned_client, listed):
    from mailer.delivery import QUEUED_TOO_LONG

    listed.return_value = {SENT_UID: _row("queued", age=QUEUED_TOO_LONG + timedelta(minutes=5))}

    response = await versioned_client.get("/api/v2/invitees")

    by_uid = {i["uid"]: i["emailDelivery"] for i in response.json()}
    assert by_uid[SENT_UID]["status"] == "failed"
    assert by_uid[SENT_UID]["timedOut"] is True
    assert by_uid[SENT_UID]["error"] is None
