"""An open invitations list hears about its emails as they change.

The list is loaded once, but an email's story continues after: the worker
settles it (sent, or failed), then the mail service's webhook reports a
delivery or a bounce seconds to minutes later. The administrator who just
sent an invitation to a mailbox that does not exist kept seeing "Envoyé"
until they opened the invitation's page.

No polling: each change is pushed.

* mailer.live.publish_delivery: every time an EmailDelivery's status moves
  (mark_result in the worker, apply_event from the webhook), the change is
  published on Redis -- several FastAPI worker processes serve the streams,
  so an in-process queue would reach only one of them. Publishing must never
  break sending: a Redis hiccup is logged, not raised.
* GET /api/v2/invitees/events: a Server-Sent Events stream, guarded like the
  list it feeds. It passes on only the changes of the requesting site's
  organization -- another organization's invitees are not this
  administrator's business.
"""
import json
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async

from mailer import live
from mailer.delivery import apply_event, mark_result, record_queued
from mailer.providers.base import DeliveryEvent, EventKind

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]

UID = "a" * 32
ORG = "0" * 32


@contextmanager
def captured():
    """The published messages, with the invitee's organization resolved to ORG."""
    sent = []
    redis = MagicMock()
    redis.publish.side_effect = lambda channel, message: sent.append((channel, json.loads(message)))
    with patch("mailer.live._redis", return_value=redis), \
            patch("mailer.live.organization_of", return_value=ORG):
        yield sent


class TestEveryChangeIsPublished:
    async def test_the_workers_answer(self):
        with captured() as sent:
            await sync_to_async(lambda: mark_result(record_queued(UID, "a@x.org").id, {"id": "<m@x>"}))()
        [(channel, message)] = sent
        assert channel == live.CHANNEL
        assert message["organization"] == ORG
        assert message["invitee_uid"] == UID
        assert message["emailDelivery"]["status"] == "sent"

    async def test_a_bounce_from_the_webhook(self):
        @sync_to_async
        def bounce():
            row = record_queued(UID, "a@x.org")
            mark_result(row.id, {"id": "<m@x>"})
            apply_event(DeliveryEvent(
                provider="mailgun", event_id="e1", kind=EventKind.BOUNCED, recipient="a@x.org",
                occurred_at=0, metadata={"delivery_id": str(row.id)}, detail="550 User unknown",
            ))

        with captured() as sent:
            await bounce()
        assert [m["emailDelivery"]["status"] for _, m in sent] == ["sent", "bounced"]
        assert "User unknown" in sent[-1][1]["emailDelivery"]["error"]

    async def test_redis_down_does_not_break_sending(self):
        broken = MagicMock()
        broken.publish.side_effect = ConnectionError("redis down")
        with patch("mailer.live._redis", return_value=broken), patch("mailer.live.organization_of", return_value=ORG):
            row = await sync_to_async(record_queued)(UID, "a@x.org")
            await sync_to_async(mark_result)(row.id, {"id": "<m@x>"})  # must not raise
        await sync_to_async(row.refresh_from_db)()
        assert row.status == "sent"


class TestTheStream:
    def test_only_the_organizations_own_changes(self):
        mine = json.dumps({"organization": ORG, "invitee_uid": UID, "emailDelivery": {"status": "bounced"}})
        theirs = json.dumps({"organization": "1" * 32, "invitee_uid": "b" * 32, "emailDelivery": {}})
        assert live.for_organization(mine, ORG) == {"invitee_uid": UID, "emailDelivery": {"status": "bounced"}}
        assert live.for_organization(theirs, ORG) is None
        assert live.for_organization("not json", ORG) is None

    def test_in_server_sent_events_format(self):
        frame = live.sse("delivery", {"invitee_uid": UID})
        assert frame == f'event: delivery\ndata: {{"invitee_uid": "{UID}"}}\n\n'

    @pytest.mark.parametrize("role", ["staff", "registered"])
    async def test_guarded_like_the_list(self, versioned_client, patch_jwt, jwt_staff, role):
        from fastapi import HTTPException
        with patch_jwt(jwt_staff), \
                patch("api.routers.invitees.authorize_api", new_callable=AsyncMock,
                      side_effect=HTTPException(status_code=403)):
            r = await versioned_client.get("/api/v2/invitees/events")
        assert r.status_code == 403


class TestPublishedWhereverItHappens:
    """mark_result runs in the Celery worker, a webhook replay in the Django
    shell: neither container has FastAPI, so the message must be built without
    the api package. Importing api.types there failed, and the "never raise"
    guard hid it: nothing was ever published from the worker."""

    async def test_without_the_api_package(self):
        import sys
        with captured() as sent, patch.dict(sys.modules, {"api": None, "api.types": None, "api.types.invitee": None}):
            await sync_to_async(lambda: mark_result(record_queued(UID, "a@x.org").id, {"id": "<m@x>"}))()
        assert [m["emailDelivery"]["status"] for _, m in sent] == ["sent"]

    async def test_the_api_describes_a_delivery_the_same_way(self):
        from api.types.invitee import EmailDelivery
        from mailer.delivery import delivery_payload

        row = await sync_to_async(record_queued)(UID, "a@x.org")
        assert EmailDelivery.from_row(row).model_dump(mode="json") == delivery_payload(row)


class FakePubSub:
    """Hands out the queued messages, then nothing (a quiet channel)."""

    def __init__(self, *messages):
        self.messages = list(messages)

    async def get_message(self, ignore_subscribe_messages=True, timeout=0):
        return {"type": "message", "data": self.messages.pop(0)} if self.messages else None


async def frames(gen, limit=10):
    out = []
    async for frame in gen:
        out.append(frame)
        if len(out) >= limit:
            break
    return out


class TestAStreamEnds:
    """An open stream must never hold the server: uvicorn waits for every
    connection to close before it stops, and an endless stream made a
    --reload (and would make a redeploy) hang -- the backend answered 504 to
    everything meanwhile."""

    async def test_when_the_server_stops(self):
        import asyncio
        stopping = asyncio.Event()
        stopping.set()
        got = await frames(live.stream_changes(FakePubSub(), ORG, AsyncMock(return_value=False), stopping))
        assert got == ["retry: 5000\n\n"]

    async def test_when_the_client_leaves(self):
        import asyncio
        got = await frames(live.stream_changes(FakePubSub(), ORG, AsyncMock(return_value=True), asyncio.Event()))
        assert got == ["retry: 5000\n\n"]

    async def test_passing_on_its_organizations_changes_meanwhile(self):
        import asyncio
        mine = json.dumps({"organization": ORG, "invitee_uid": UID, "emailDelivery": {"status": "bounced"}})
        theirs = json.dumps({"organization": "1" * 32, "invitee_uid": "b" * 32, "emailDelivery": {}})
        left = AsyncMock(side_effect=[False, False, True])
        got = await frames(live.stream_changes(FakePubSub(theirs, mine), ORG, left, asyncio.Event()))
        assert got[1:] == [live.sse("delivery", {"invitee_uid": UID, "emailDelivery": {"status": "bounced"}})]


def test_the_stop_signal_is_noticed_and_passed_on():
    """Our handler sets the event and still calls uvicorn's."""
    import asyncio
    import os
    import signal

    from api import stopping

    called = []
    previous = signal.signal(signal.SIGTERM, lambda signum, frame: called.append(signum))
    try:
        async def scenario():
            event = stopping.install()
            os.kill(os.getpid(), signal.SIGTERM)
            await asyncio.wait_for(event.wait(), timeout=2)
            return event.is_set()

        assert asyncio.run(scenario()) is True
        assert called == [signal.SIGTERM]
    finally:
        signal.signal(signal.SIGTERM, previous)
