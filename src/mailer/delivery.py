"""Whether an invitation's email went out: EmailDelivery rows.

record_queued() when the email is handed on, mark_result() with what
mailer.main.send_single_email answered. Synchronous: the Celery task and the
batch path call them directly, the async single-invite path through
sync_to_async.
"""

import logging
from datetime import timedelta

from django.utils import timezone

from mailer.models import EmailDelivery

logger = logging.getLogger(__name__)

# A queued email nobody settled after this long is reported as failed (timed
# out): the worker may have failed before it could say so -- a stale worker
# rejecting a new argument, a crash, a lost message. Only time reveals those.
QUEUED_TOO_LONG = timedelta(minutes=15)
ERROR_MAX_LENGTH = 1000


def record_queued(invitee_uid: str, to_address: str) -> EmailDelivery:
    return EmailDelivery.objects.create(invitee_uid=invitee_uid, to_address=to_address)


def mark_result(delivery_id: int, result: dict | None) -> None:
    """Settle a delivery from send_single_email's answer: a Mailgun message
    id means accepted; anything else is a failure, with what was said."""
    result = result or {}
    if result.get("id"):
        fields = {"status": EmailDelivery.Status.SENT, "provider_message_id": str(result["id"])[:255], "error": ""}
    else:
        reason = result.get("error") or "No answer from the mail service"
        status_code = result.get("status_code")
        error = f"{status_code}: {reason}" if status_code else str(reason)
        fields = {"status": EmailDelivery.Status.FAILED, "error": error[:ERROR_MAX_LENGTH]}
    updated = EmailDelivery.objects.filter(id=delivery_id).update(updated=timezone.now(), **fields)
    if not updated:
        logger.warning(f"EmailDelivery {delivery_id} not found; result not recorded: {fields['status']}")


def timed_out(row) -> bool:
    """Queued, and nobody said how it ended within QUEUED_TOO_LONG."""
    return row.status == EmailDelivery.Status.QUEUED and timezone.now() - row.updated > QUEUED_TOO_LONG


def delivery_status(row) -> str:
    """queued | sent | failed -- an email that timed out counts as failed: for
    the administrator it is the same thing, and the answer is to resend."""
    return EmailDelivery.Status.FAILED.value if timed_out(row) else row.status


def latest_deliveries(invitee_uids) -> dict[str, EmailDelivery]:
    """The most recent attempt for each invitation that has one."""
    uids = list(invitee_uids)
    if not uids:
        return {}
    latest: dict[str, EmailDelivery] = {}
    for row in EmailDelivery.objects.filter(invitee_uid__in=uids).order_by("invitee_uid", "-created", "-id"):
        latest.setdefault(row.invitee_uid, row)
    return latest


def resend_refusal(invitee, latest) -> str | None:
    """Why an invitation's email may not be sent again, as a code, or None.

    used / disabled: the invitation can no longer be redeemed, so the email
    would invite to nothing. already_queued: the previous email is still on
    its way -- a double click must not send two. A queued email that timed
    out counts as failed, and may be sent again: it probably never left.
    """
    if getattr(invitee, "redeemedAt", None):
        return "used"
    if getattr(invitee, "active", True) is False:
        return "disabled"
    if latest is not None and delivery_status(latest) == "queued":
        return "already_queued"
    return None
