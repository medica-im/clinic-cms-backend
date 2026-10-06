"""What became of an email after the mail service accepted it.

"Sent" only ever meant that Mailgun took the message. An invitation to a
mailbox that does not exist was accepted, then bounced a few seconds later
(550 5.1.1 User unknown) -- and the invitation page kept saying "E-mail
envoyé", because nothing told the app. The service reports what happens next
by calling a webhook:

    POST /api/v2/mail/events/mailgun

* **Correlated by our own id.** Each message is sent with the EmailDelivery id
  as metadata, so an event finds its row without any provider-side lookup;
  the provider's message id is the fallback.
* **Signed, or ignored.** Anyone can POST to a public URL. The provider
  checks its signature against the deployment's signing key or an
  organization account's; a forged event changes nothing.
* **Once.** The service retries a webhook it thinks failed; each event is
  stored by the provider's own event id, and a second copy is a no-op.
* **Never backwards.** Events can arrive out of order: a late "deferred"
  must not undo "delivered", nothing undoes "bounced". A spam complaint
  comes after delivery and does replace it.
* **Host-independent.** The URL is each server's own hostname
  (dev.medica.im, production.medica.im...), none of which has a Site row, so
  the endpoint looks nothing up from the Host header.

The provider translates its payload into a neutral DeliveryEvent; the rest
of this file never sees a Mailgun field outside the payloads it builds.
"""
import hashlib
import hmac
import json
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from django.test import override_settings

from mailer.delivery import mark_result, record_queued
from mailer.models import EmailDelivery, EmailEvent

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]

KEY = "test-webhook-signing-key"
URL = "/api/v2/mail/events/mailgun"
UID = "a" * 32
MESSAGE_ID = "20261005200610.ae6417e87b0166cf@mail.medica.im"


def signed(event_data: dict, key: str = KEY) -> dict:
    timestamp, token = str(int(time.time())), uuid.uuid4().hex
    signature = hmac.new(key.encode(), f"{timestamp}{token}".encode(), hashlib.sha256).hexdigest()
    return {"signature": {"timestamp": timestamp, "token": token, "signature": signature}, "event-data": event_data}


def event(kind: str, delivery_id=None, **extra) -> dict:
    data = {
        "id": uuid.uuid4().hex,
        "event": kind,
        "timestamp": time.time(),
        "recipient": "test23244@medica.im",
        "message": {"headers": {"message-id": MESSAGE_ID}},
        "user-variables": {"delivery_id": str(delivery_id)} if delivery_id is not None else {},
    }
    data.update(extra)
    return data


BOUNCE = {
    "severity": "permanent", "reason": "bounce",
    "delivery-status": {"code": 550, "message": "5.1.1 <test23244@medica.im>: Recipient address rejected: User unknown"},
}
DEFERRAL = {"severity": "temporary", "reason": "generic", "delivery-status": {"code": 451, "message": "try later"}}


@sync_to_async
def a_sent_delivery() -> EmailDelivery:
    row = record_queued(UID, "test23244@medica.im")
    mark_result(row.id, {"id": f"<{MESSAGE_ID}>", "message": "Queued. Thank you."})
    row.refresh_from_db()
    return row


@sync_to_async
def reload(row) -> EmailDelivery:
    row.refresh_from_db()
    return row


async def post(client, payload):
    return await client.post(URL, content=json.dumps(payload), headers={"content-type": "application/json"})


@pytest.fixture(autouse=True)
def signing_key():
    with override_settings(MAILGUN_WEBHOOK_SIGNING_KEY=KEY):
        yield


class TestWhatHappenedNext:
    async def test_a_bounce_says_the_address_was_rejected(self, versioned_client):
        row = await a_sent_delivery()
        r = await post(versioned_client, signed(event("failed", row.id, **BOUNCE)))
        assert r.status_code == 200, r.text
        row = await reload(row)
        assert row.status == "bounced"
        assert "User unknown" in row.error

    async def test_a_delivery(self, versioned_client):
        row = await a_sent_delivery()
        await post(versioned_client, signed(event("delivered", row.id)))
        assert (await reload(row)).status == "delivered"

    async def test_a_temporary_failure_is_a_deferral(self, versioned_client):
        row = await a_sent_delivery()
        await post(versioned_client, signed(event("failed", row.id, **DEFERRAL)))
        assert (await reload(row)).status == "deferred"

    async def test_a_spam_complaint(self, versioned_client):
        row = await a_sent_delivery()
        await post(versioned_client, signed(event("delivered", row.id)))
        await post(versioned_client, signed(event("complained", row.id)))
        assert (await reload(row)).status == "complained"

    async def test_dropped_by_the_services_own_suppression_list(self, versioned_client):
        row = await a_sent_delivery()
        await post(versioned_client, signed(event("failed", row.id, severity="permanent", reason="suppress-bounce")))
        assert (await reload(row)).status == "suppressed"

    async def test_found_by_message_id_without_our_metadata(self, versioned_client):
        """Mail sent before the metadata existed still gets its events."""
        row = await a_sent_delivery()
        await post(versioned_client, signed(event("failed", None, **BOUNCE)))
        assert (await reload(row)).status == "bounced"

    async def test_the_history_is_kept(self, versioned_client):
        row = await a_sent_delivery()
        await post(versioned_client, signed(event("failed", row.id, **DEFERRAL)))
        await post(versioned_client, signed(event("delivered", row.id)))
        kinds = await sync_to_async(lambda: list(
            EmailEvent.objects.filter(delivery=row).order_by("occurred_at").values_list("kind", flat=True)
        ))()
        assert kinds == ["deferred", "delivered"]


class TestNeverBackwards:
    async def test_a_late_deferral_does_not_undo_a_delivery(self, versioned_client):
        row = await a_sent_delivery()
        await post(versioned_client, signed(event("delivered", row.id)))
        await post(versioned_client, signed(event("failed", row.id, **DEFERRAL)))
        assert (await reload(row)).status == "delivered"

    async def test_nothing_undoes_a_bounce(self, versioned_client):
        row = await a_sent_delivery()
        await post(versioned_client, signed(event("failed", row.id, **BOUNCE)))
        await post(versioned_client, signed(event("delivered", row.id)))
        assert (await reload(row)).status == "bounced"


class TestOnlyTheServiceAndOnlyOnce:
    async def test_a_forged_event_changes_nothing(self, versioned_client):
        row = await a_sent_delivery()
        r = await post(versioned_client, signed(event("failed", row.id, **BOUNCE), key="not-the-key"))
        assert r.status_code == 401
        assert (await reload(row)).status == "sent"

    async def test_an_unsigned_one_neither(self, versioned_client):
        row = await a_sent_delivery()
        r = await post(versioned_client, {"event-data": event("failed", row.id, **BOUNCE)})
        assert r.status_code == 401
        assert (await reload(row)).status == "sent"

    async def test_an_organization_accounts_key_is_accepted(self, versioned_client, site):
        from facility.models import Organization
        from mailer.models import MailgunAccount

        @sync_to_async
        def account():
            org = Organization.objects.create(name="own-mailgun-org", site=site)
            MailgunAccount.objects.create(
                organization=org, domain="mail.example.org", region="eu", sending_key_id="k", api_key="k",
                from_email="o@example.org", webhook_signing_key="org-signing-key", active=True,
            )

        await account()
        row = await a_sent_delivery()
        r = await post(versioned_client, signed(event("delivered", row.id), key="org-signing-key"))
        assert r.status_code == 200
        assert (await reload(row)).status == "delivered"

    async def test_a_retried_event_is_applied_once(self, versioned_client):
        row = await a_sent_delivery()
        payload = signed(event("delivered", row.id))
        await post(versioned_client, payload)
        r = await post(versioned_client, payload)
        assert r.status_code == 200
        assert await sync_to_async(EmailEvent.objects.filter(delivery=row).count)() == 1

    async def test_an_event_for_mail_we_did_not_send_is_acknowledged_and_ignored(self, versioned_client):
        """Answered 200, or the service would retry it for hours."""
        r = await post(versioned_client, signed(event("delivered", 999999, message={"headers": {"message-id": "x@y"}})))
        assert r.status_code == 200

    async def test_an_unknown_provider_is_not_found(self, versioned_client):
        r = await versioned_client.post("/api/v2/mail/events/carrier-pigeon", json={})
        assert r.status_code == 404


class TestTheMessageCarriesOurId:
    def _ok(self):
        response = MagicMock(status_code=200, headers={})
        response.json.return_value = {"id": "<m@x>", "message": "Queued"}
        return response

    async def test_the_delivery_id_and_tag_go_out_with_it(self):
        from mailer.main import send_single_email

        with patch("mailer.providers.mailgun.requests.post", return_value=self._ok()) as post_:
            await sync_to_async(send_single_email)(
                "who@example.org", "S", "t", metadata={"delivery_id": 42}, tags=["invitation"],
            )
        data = post_.call_args.kwargs["data"]
        assert data["v:delivery_id"] == "42"
        assert data["o:tag"] == ["invitation"]

    async def test_the_invitation_task_sends_its_delivery_id(self):
        from mailer.tasks import send_single_email_task

        with patch("mailer.tasks.send_single_email", return_value={"id": "<m@x>"}) as send, \
                patch("mailer.tasks.mark_result"):
            await sync_to_async(send_single_email_task)("who@example.org", "S", "t", delivery_id=42)
        assert send.call_args.kwargs["metadata"] == {"delivery_id": 42}
        assert send.call_args.kwargs["tags"] == ["invitation"]

    async def test_the_batch_sends_its_delivery_id(self):
        from types import SimpleNamespace
        from access.tasks import _send_notification_email
        from tests.test_invitations_send_per_organization import FakeSite

        org = SimpleNamespace(id=1, mailgun_account=None, reply_to_email="")
        with patch("django.contrib.sites.models.Site.objects.get", return_value=FakeSite()), \
                patch("facility.models.Organization.objects.get", return_value=org), \
                patch("mailer.templating.get_template"), \
                patch("mailer.templating.render_email", return_value=SimpleNamespace(subject="S", text="t", html=None)), \
                patch("mailer.templating.invitation_context", return_value={}), \
                patch("mailer.config.get_sender"), \
                patch("mailer.main.send_single_email", return_value={"id": "<m@x>"}) as send, \
                patch("mailer.delivery.record_queued", return_value=SimpleNamespace(id=7)), \
                patch("mailer.delivery.mark_result"):
            await sync_to_async(_send_notification_email)("who@example.org", "Who", FakeSite.domain, invitee_uid=UID)
        assert send.call_args.kwargs["metadata"] == {"delivery_id": 7}
