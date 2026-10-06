"""Bad email addresses: remembered, not retried blindly, shown, fixable.

An invitation to a mailbox that does not exist bounces; retrying it is
useless and hurts the sending domain's reputation. And the people who can fix
the address are the organization's administrators -- they know the member.

* **Remembered** (mailer.suppression, EmailSuppression): a bounce, or an
  address the mail service refused as written, is remembered for every
  organization -- the address does not work, whoever sends. A spam complaint
  or an unsubscribe is the person's refusal of *one* organization's mail and
  is remembered for that organization only. A later delivery to a bounced
  address (the mailbox was reopened) forgets the bounce.
* **Not retried blindly**: a new invitation or a batch skips a remembered
  address -- the delivery is "suppressed", with why. The administrator's
  resend answers 409 with the reason and date; with force (the address was
  checked and is right) it goes. A refusal of the organization's mail is
  never overridden.
* **Shown**: each invitation carries addressIssue, in the list, on its page
  and in the batch report, so an administrator sees it before trying again.
* **Fixable**: correcting the address of an unused invitation sends it to the
  new address straight away.
"""
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async

from mailer import suppression
from mailer.delivery import apply_event, mark_result, record_queued
from mailer.models import EmailDelivery, EmailSuppression
from mailer.providers.base import DeliveryEvent, EventKind

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]

UID = "a" * 32
ADDRESS = "nobody@medica.im"


def event(kind, delivery_id=None, recipient=ADDRESS, detail="550 5.1.1 User unknown"):
    return DeliveryEvent(
        provider="mailgun", event_id=uuid.uuid4().hex, kind=kind, recipient=recipient, occurred_at=0,
        metadata={"delivery_id": str(delivery_id)} if delivery_id else {}, detail=detail,
    )


@sync_to_async
def sent_delivery(address=ADDRESS, uid=UID):
    row = record_queued(uid, address)
    mark_result(row.id, {"id": f"<{uuid.uuid4().hex}@x>"})
    return row


@pytest.fixture
def organizations(site):
    """Two organizations; invitations of UID belong to the first."""
    from django.contrib.sites.models import Site
    from facility.models import Organization

    other_site, _ = Site.objects.get_or_create(domain="other.example", defaults={"name": "Other"})
    mine = Organization.objects.create(name="bad-addr-org", site=site, neomodel_uid=uuid.uuid4())
    theirs = Organization.objects.create(name="bad-addr-other", site=other_site, neomodel_uid=uuid.uuid4())
    with patch("mailer.live.organization_of", return_value=mine.neomodel_uid.hex), \
            patch("mailer.live._redis", return_value=MagicMock()):
        yield SimpleNamespace(mine=mine, theirs=theirs)


# --- Remembered ----------------------------------------------------------------


class TestRemembered:
    async def test_a_bounce_for_every_organization(self, organizations):
        row = await sent_delivery()
        await sync_to_async(apply_event)(event(EventKind.BOUNCED, row.id))
        found = await sync_to_async(suppression.blocking)(ADDRESS, organizations.theirs)
        assert (found.reason, found.organization_id) == ("bounced", None)
        assert "User unknown" in found.detail

    async def test_bounces_are_counted_not_duplicated(self, organizations):
        row = await sent_delivery()
        await sync_to_async(apply_event)(event(EventKind.BOUNCED, row.id))
        await sync_to_async(apply_event)(event(EventKind.BOUNCED, row.id))
        rows = await sync_to_async(lambda: list(EmailSuppression.objects.filter(address=ADDRESS)))()
        assert [(r.reason, r.count) for r in rows] == [("bounced", 2)]

    async def test_the_address_is_compared_without_case(self, organizations):
        row = await sent_delivery()
        await sync_to_async(apply_event)(event(EventKind.BOUNCED, row.id, recipient="NoBody@Medica.IM"))
        assert await sync_to_async(suppression.blocking)("nobody@medica.im", organizations.mine)

    async def test_dropped_by_the_services_own_list(self, organizations):
        row = await sent_delivery()
        await sync_to_async(apply_event)(event(EventKind.SUPPRESSED, row.id))
        assert (await sync_to_async(suppression.blocking)(ADDRESS, organizations.mine)).reason == "bounced"

    async def test_refused_as_written(self, organizations):
        row = await sync_to_async(record_queued)(UID, ADDRESS)
        await sync_to_async(mark_result)(row.id, {
            "error": "'to' parameter is not a valid address", "status_code": 400, "error_kind": "invalid_request",
        })
        assert (await sync_to_async(suppression.blocking)(ADDRESS, organizations.mine)).reason == "refused"

    async def test_a_service_outage_is_not_the_addresses_fault(self, organizations):
        row = await sync_to_async(record_queued)(UID, ADDRESS)
        await sync_to_async(mark_result)(row.id, {"error": "down", "status_code": 503, "error_kind": "provider_unavailable"})
        assert await sync_to_async(suppression.blocking)(ADDRESS, organizations.mine) is None

    async def test_a_complaint_for_this_organization_only(self, organizations):
        row = await sent_delivery()
        await sync_to_async(apply_event)(event(EventKind.COMPLAINED, row.id))
        mine = await sync_to_async(suppression.blocking)(ADDRESS, organizations.mine)
        assert (mine.reason, mine.organization_id) == ("complained", organizations.mine.id)
        assert await sync_to_async(suppression.blocking)(ADDRESS, organizations.theirs) is None

    async def test_an_unsubscribe_too(self, organizations):
        row = await sent_delivery()
        await sync_to_async(apply_event)(event(EventKind.UNSUBSCRIBED, row.id))
        assert (await sync_to_async(suppression.blocking)(ADDRESS, organizations.mine)).reason == "unsubscribed"

    async def test_a_later_delivery_forgets_the_bounce(self, organizations):
        row = await sent_delivery()
        await sync_to_async(apply_event)(event(EventKind.BOUNCED, row.id))
        again = await sent_delivery()
        await sync_to_async(apply_event)(event(EventKind.DELIVERED, again.id))
        assert await sync_to_async(suppression.blocking)(ADDRESS, organizations.mine) is None

    async def test_but_not_a_complaint(self, organizations):
        row = await sent_delivery()
        await sync_to_async(apply_event)(event(EventKind.COMPLAINED, row.id))
        again = await sent_delivery()
        await sync_to_async(apply_event)(event(EventKind.DELIVERED, again.id))
        assert (await sync_to_async(suppression.blocking)(ADDRESS, organizations.mine)).reason == "complained"


# --- Not retried blindly ----------------------------------------------------------


@sync_to_async
def remember(organization=None, reason="bounced"):
    return suppression.record(ADDRESS, reason, organization=organization, detail="550 5.1.1 User unknown")


class TestAutomaticSendsSkipIt:
    async def test_a_new_invitation(self, organizations):
        from mailer.tasks import send_single_email_task

        await remember()
        row = await sync_to_async(record_queued)(UID, ADDRESS)
        with patch("mailer.tasks.send_single_email") as send:
            await sync_to_async(send_single_email_task)(ADDRESS, "S", "t", organization_id=organizations.mine.id, delivery_id=row.id)
        send.assert_not_called()
        row = await sync_to_async(EmailDelivery.objects.get)(id=row.id)
        assert row.status == "suppressed"
        assert "User unknown" in row.error

    async def test_unless_forced(self, organizations):
        from mailer.tasks import send_single_email_task

        await remember()
        row = await sync_to_async(record_queued)(UID, ADDRESS)
        with patch("mailer.tasks.send_single_email", return_value={"id": "<m@x>"}) as send:
            await sync_to_async(send_single_email_task)(
                ADDRESS, "S", "t", organization_id=organizations.mine.id, delivery_id=row.id, force_send=True,
            )
        send.assert_called_once()

    async def test_another_organizations_refusal_does_not_block_this_one(self, organizations):
        from mailer.tasks import send_single_email_task

        await remember(organizations.theirs, "complained")
        row = await sync_to_async(record_queued)(UID, ADDRESS)
        with patch("mailer.tasks.send_single_email", return_value={"id": "<m@x>"}) as send:
            await sync_to_async(send_single_email_task)(ADDRESS, "S", "t", organization_id=organizations.mine.id, delivery_id=row.id)
        send.assert_called_once()

    async def test_a_batch(self, organizations, site):
        from access.tasks import _send_notification_email

        await remember()
        with patch("mailer.main.send_single_email") as send:
            ok = await sync_to_async(_send_notification_email)(ADDRESS, "", site.domain, invitee_uid=UID)
        send.assert_not_called()
        assert ok is False
        row = await sync_to_async(lambda: EmailDelivery.objects.filter(invitee_uid=UID).latest("id"))()
        assert row.status == "suppressed"


# --- The administrator's resend ------------------------------------------------------


class FakeNode:
    """An Invitee node: attributes in, __properties__ out, save() returns it."""

    def __init__(self, **fields):
        self.__dict__.update(fields)

    @property
    def __properties__(self):
        return {k: v for k, v in self.__dict__.items()}

    async def save(self):
        return self


@contextmanager
def invitation(site, email=ADDRESS, redeemed=False):
    """An invitation node of this site's organization, behind the guards."""
    node = FakeNode(uid=UID, email=email, name="Who", role="staff", active=True,
                    redeemedAt=1790000000000 if redeemed else None)
    with patch("api.routers.invitees.authorize_api", new_callable=AsyncMock), \
            patch("api.routers.invitees.verify_invitee_ownership", new_callable=AsyncMock), \
            patch("api.routers.invitees.get_site_from_request", new_callable=AsyncMock, return_value=site), \
            patch("api.routers.invitees.AsyncInvitee.nodes", MagicMock(get=AsyncMock(return_value=node))), \
            patch("api.routers.invitees.notification_email", new_callable=AsyncMock) as notify:
        yield SimpleNamespace(node=node, notify=notify)


class TestTheResend:
    async def test_a_rejected_address_says_so(self, versioned_client, patch_jwt, jwt_administrator, site, organizations):
        await remember()
        with patch_jwt(jwt_administrator), invitation(site) as inv:
            r = await versioned_client.post(f"/api/v2/invitees/{UID}/resend")
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert detail["code"] == "address_rejected"
        assert detail["reason"] == "bounced"
        assert "User unknown" in detail["detail"]
        assert detail["since"]
        inv.notify.assert_not_called()

    async def test_and_goes_when_forced(self, versioned_client, patch_jwt, jwt_administrator, site, organizations):
        await remember()
        with patch_jwt(jwt_administrator), invitation(site) as inv:
            r = await versioned_client.post(f"/api/v2/invitees/{UID}/resend", json={"force": True})
        assert r.status_code == 200, r.text
        assert inv.notify.call_args.kwargs.get("force") is True

    async def test_a_refusal_of_the_organizations_mail_is_never_overridden(
        self, versioned_client, patch_jwt, jwt_administrator, site, organizations
    ):
        await remember(organizations.mine, "complained")
        with patch_jwt(jwt_administrator), invitation(site) as inv:
            r = await versioned_client.post(f"/api/v2/invitees/{UID}/resend", json={"force": True})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "address_opted_out"
        inv.notify.assert_not_called()


# --- Fixing the address ------------------------------------------------------------


class TestCorrectingTheAddress:
    async def test_sends_to_the_new_address(self, versioned_client, patch_jwt, jwt_administrator, site, organizations):
        with patch_jwt(jwt_administrator), invitation(site) as inv:
            r = await versioned_client.patch(f"/api/v2/invitees/{UID}", json={"email": "right@medica.im"})
        assert r.status_code == 200, r.text
        sent_to = inv.notify.call_args.args[0]
        assert sent_to.email == "right@medica.im"

    async def test_not_when_the_address_is_unchanged(self, versioned_client, patch_jwt, jwt_administrator, site, organizations):
        with patch_jwt(jwt_administrator), invitation(site) as inv:
            await versioned_client.patch(f"/api/v2/invitees/{UID}", json={"email": ADDRESS, "name": "New name"})
        inv.notify.assert_not_called()

    async def test_not_for_a_used_invitation(self, versioned_client, patch_jwt, jwt_administrator, site, organizations):
        with patch_jwt(jwt_administrator), invitation(site, redeemed=True) as inv:
            await versioned_client.patch(f"/api/v2/invitees/{UID}", json={"email": "right@medica.im"})
        inv.notify.assert_not_called()


# --- Shown ----------------------------------------------------------------------------


class TestShown:
    async def test_on_the_invitation(self, versioned_client, patch_jwt, jwt_administrator, site, organizations):
        await remember()
        with patch_jwt(jwt_administrator), invitation(site), \
                patch("api.routers.invitees.adb.cypher_query", new_callable=AsyncMock,
                      return_value=([[{"uid": UID, "email": ADDRESS, "role": "staff", "active": True}, None]], None)):
            r = await versioned_client.get(f"/api/v2/invitees/{UID}")
        issue = r.json()["addressIssue"]
        assert issue["reason"] == "bounced"
        assert "User unknown" in issue["detail"]
        assert issue["since"]

    async def test_not_another_organizations_refusal(self, versioned_client, patch_jwt, jwt_administrator, site, organizations):
        await remember(organizations.theirs, "complained")
        with patch_jwt(jwt_administrator), invitation(site), \
                patch("api.routers.invitees.adb.cypher_query", new_callable=AsyncMock,
                      return_value=([[{"uid": UID, "email": ADDRESS, "role": "staff", "active": True}, None]], None)):
            r = await versioned_client.get(f"/api/v2/invitees/{UID}")
        assert r.json()["addressIssue"] is None

    async def test_in_the_batch_report(self, versioned_client, patch_jwt, jwt_administrator, organizations):
        from access.models import BatchInviteeJob

        await remember()
        entry_uid = organizations.mine.neomodel_uid.hex
        job = await BatchInviteeJob.objects.acreate(
            organization_neomodel_uid=entry_uid, user_uid="u", total_rows=2, processed_rows=2,
            role="staff", send_emails=True, status=BatchInviteeJob.Status.COMPLETED,
            summary=[
                {"row": 1, "email": ADDRESS, "status": "created", "invitee_uid": UID},
                {"row": 2, "email": "fine@medica.im", "status": "created", "invitee_uid": "b" * 32},
            ],
        )
        with patch_jwt(jwt_administrator), \
                patch("api.routers.batch_invitees.authorize_api", new_callable=AsyncMock), \
                patch("api.routers.batch_invitees._get_organization_entry_uid", new_callable=AsyncMock,
                      return_value=(entry_uid, "testserver")):
            r = await versioned_client.get(f"/api/v2/batch-invitees/{job.uid}")
        rows = {row["row"]: row for row in r.json()["summary"]}
        assert rows[1]["addressIssue"]["reason"] == "bounced"
        assert rows[2]["addressIssue"] is None
        assert r.json()["address_issue_count"] == 1
