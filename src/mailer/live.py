"""Pushing email delivery changes to the invitation lists that are open.

publish_delivery() is called wherever an EmailDelivery's status moves
(mailer.delivery: mark_result in the worker, apply_event from the webhook)
and publishes the change on Redis, tagged with the invitee's organization.
GET /api/v2/invitees/events (api.routers.invitees) subscribes and streams
the changes of the requesting organization only, as Server-Sent Events.

Redis, not an in-process queue: the webhook, the worker and the streams run
in different processes. Publishing never raises -- a mail must not fail
because nobody could be told about it. See tests/api/test_delivery_push.py.
"""
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

CHANNEL = "mail:delivery-changes"


def _redis():
    import redis
    return redis.Redis(host=settings.REDIS_HOST, port=int(settings.REDIS_PORT), socket_timeout=2)


def redis_url() -> str:
    return f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"


def organization_of(invitee_uid: str) -> str | None:
    """The uid of the organization Entry the invitation belongs to."""
    from neomodel import db
    rows, _ = db.cypher_query(
        "MATCH (:Invitee {uid: $uid})-[:INVITED_TO]->(e:Entry) RETURN e.uid LIMIT 1", {"uid": invitee_uid},
    )
    return rows[0][0] if rows else None


def publish_delivery(row) -> None:
    """Tell the open lists where this invitation's email stands now."""
    try:
        # Not api.types: the worker and the Django shell have no FastAPI.
        from mailer.delivery import delivery_payload

        message = {
            "organization": organization_of(row.invitee_uid),
            "invitee_uid": row.invitee_uid,
            "emailDelivery": delivery_payload(row),
        }
        _redis().publish(CHANNEL, json.dumps(message))
    except Exception as e:  # noqa: BLE001 -- never let telling break sending
        logger.warning(f"Could not publish the delivery change of {row.invitee_uid}: {e}")


def for_organization(raw, organization_uid: str) -> dict | None:
    """The change, without its routing, if it concerns this organization."""
    try:
        message = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(message, dict) or message.get("organization") != organization_uid:
        return None
    return {"invitee_uid": message.get("invitee_uid"), "emailDelivery": message.get("emailDelivery")}


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# How often a stream checks that its client is still there and the server is
# not stopping, and how often it sends a comment so proxies (60 s read
# timeout) keep an idle stream open.
CHECK_EVERY = 1
HEARTBEAT = 20


async def stream_changes(pubsub, organization_uid: str, is_disconnected, stopping):
    """The SSE frames of one invitations list: this organization's changes.

    Ends when the client leaves or the server is stopping -- never holds the
    process (api/stopping.py); EventSource then reconnects by itself.
    """
    yield "retry: 5000\n\n"
    quiet = 0
    while not stopping.is_set() and not await is_disconnected():
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=CHECK_EVERY)
        if message is None:
            quiet += CHECK_EVERY
            if quiet >= HEARTBEAT:
                quiet = 0
                yield ": ping\n\n"
            continue
        change = for_organization(message.get("data"), organization_uid)
        if change is not None:
            yield sse("delivery", change)
