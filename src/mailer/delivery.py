"""Whether an invitation's email went out: EmailDelivery rows.

record_queued() when the email is handed on, mark_result() with what
mailer.main.send_single_email answered. Synchronous: the Celery task and the
batch path call them directly, the async single-invite path through
sync_to_async.
"""

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from django.utils import timezone

from mailer.models import EmailDelivery

logger = logging.getLogger(__name__)

# A queued email nobody settled after this long is reported as failed (timed
# out): the worker may have failed before it could say so -- a stale worker
# rejecting a new argument, a crash, a lost message. Only time reveals those.
QUEUED_TOO_LONG = timedelta(minutes=15)
ERROR_MAX_LENGTH = 1000


def record_queued(invitee_uid: str, to_address: str, batch_job_uid=None) -> EmailDelivery:
    return EmailDelivery.objects.create(invitee_uid=invitee_uid, to_address=to_address, batch_job_uid=batch_job_uid)


def mark_result(delivery_id: int, result: dict | None) -> None:
    """Settle a delivery from send_single_email's answer: a provider message
    id means accepted; anything else is a failure, with what was said and its
    ErrorKind."""
    result = result or {}
    if result.get("id"):
        fields = {
            "status": EmailDelivery.Status.SENT, "provider_message_id": str(result["id"])[:255],
            "error": "", "error_kind": "",
        }
    else:
        reason = result.get("error") or "No answer from the mail service"
        status_code = result.get("status_code")
        error = f"{status_code}: {reason}" if status_code else str(reason)
        kind = result.get("error_kind") or ""
        if kind not in EmailDelivery.ErrorKind.values:
            kind = ""
        fields = {"status": EmailDelivery.Status.FAILED, "error": error[:ERROR_MAX_LENGTH], "error_kind": kind}
    updated = EmailDelivery.objects.filter(id=delivery_id).update(updated=timezone.now(), **fields)
    if not updated:
        logger.warning(f"EmailDelivery {delivery_id} not found; result not recorded: {fields['status']}")
        return
    from mailer.live import publish_delivery
    publish_delivery(EmailDelivery.objects.get(id=delivery_id))


def timed_out(row) -> bool:
    """Queued, and nobody said how it ended within QUEUED_TOO_LONG."""
    return row.status == EmailDelivery.Status.QUEUED and timezone.now() - row.updated > QUEUED_TOO_LONG


def delivery_status(row) -> str:
    """queued | sent | failed -- an email that timed out counts as failed: for
    the administrator it is the same thing, and the answer is to resend."""
    return EmailDelivery.Status.FAILED.value if timed_out(row) else row.status


def delivery_payload(row) -> dict:
    """Where an invitation's email stands, as the API and the live stream say
    it (api.types.invitee.EmailDelivery is built from this). Plain data, no
    FastAPI: the Celery worker and the Django shell publish it too."""
    return {
        "status": delivery_status(row),
        "at": row.updated.isoformat().replace("+00:00", "Z"),
        "errorKind": getattr(row, "error_kind", "") or None,
        "error": row.error or None,
        "timedOut": timed_out(row),
    }


def latest_deliveries(invitee_uids) -> dict[str, EmailDelivery]:
    """The most recent attempt for each invitation that has one."""
    uids = list(invitee_uids)
    if not uids:
        return {}
    latest: dict[str, EmailDelivery] = {}
    for row in EmailDelivery.objects.filter(invitee_uid__in=uids).order_by("invitee_uid", "-created", "-id"):
        latest.setdefault(row.invitee_uid, row)
    return latest


# What an event makes of a delivery. Final states are kept against anything
# but a spam complaint, which comes after delivery and does replace it; a late
# deferral never undoes a delivery.
_FINAL = {EmailDelivery.Status.BOUNCED, EmailDelivery.Status.COMPLAINED, EmailDelivery.Status.SUPPRESSED}
_STILL_GOING = {EmailDelivery.Status.QUEUED, EmailDelivery.Status.SENT, EmailDelivery.Status.DEFERRED}


def _next_status(current: str, kind: str) -> str:
    S = EmailDelivery.Status
    if kind == "complained":
        return S.COMPLAINED
    if current in _FINAL:
        return current
    if kind == "bounced":
        return S.BOUNCED
    if kind == "suppressed":
        return S.SUPPRESSED
    if kind == "delivered":
        return S.DELIVERED
    if kind == "deferred" and current in _STILL_GOING:
        return S.DEFERRED
    return current


def _delivery_for(event) -> EmailDelivery | None:
    """By our own id, sent as metadata; else by the provider's message id."""
    delivery_id = (event.metadata or {}).get("delivery_id")
    if delivery_id:
        try:
            return EmailDelivery.objects.get(id=int(delivery_id))
        except (EmailDelivery.DoesNotExist, ValueError, TypeError):
            pass
    if event.message_id:
        return (
            EmailDelivery.objects.filter(provider_message_id__in=[event.message_id, f"<{event.message_id}>"])
            .order_by("-created").first()
        )
    return None


def apply_event(event) -> EmailDelivery | None:
    """Record a provider event (mailer.providers.base.DeliveryEvent) once, and
    move its delivery's status on. Returns the delivery it concerned, if any."""
    from datetime import datetime, timezone as dt_timezone
    from django.db import IntegrityError, transaction
    from mailer.models import EmailEvent

    delivery = _delivery_for(event)
    try:
        with transaction.atomic():
            EmailEvent.objects.create(
                delivery=delivery,
                provider=event.provider,
                provider_event_id=event.event_id or f"{event.message_id}:{event.kind}:{event.occurred_at}",
                kind=str(event.kind),
                recipient=event.recipient[:254],
                detail=event.detail[:ERROR_MAX_LENGTH],
                occurred_at=datetime.fromtimestamp(event.occurred_at, tz=dt_timezone.utc),
                raw=event.raw if isinstance(event.raw, dict) else {},
            )
    except IntegrityError:
        logger.info(f"{event.provider} event {event.event_id} already recorded")
        return delivery
    if delivery is None:
        logger.info(f"{event.provider} {event.kind} for {event.recipient}: no delivery on record")
        return None
    status = _next_status(delivery.status, str(event.kind))
    if status != delivery.status:
        fields = {"status": status, "updated": timezone.now()}
        if status in (EmailDelivery.Status.BOUNCED, EmailDelivery.Status.DEFERRED, EmailDelivery.Status.SUPPRESSED):
            fields["error"] = event.detail[:ERROR_MAX_LENGTH]
        EmailDelivery.objects.filter(id=delivery.id).update(**fields)
        delivery.refresh_from_db()
        from mailer.live import publish_delivery
        publish_delivery(delivery)
    return delivery


@dataclass
class BatchReport:
    """Where each email of a batch stands now, and the totals."""

    by_invitee: dict[str, EmailDelivery] = field(default_factory=dict)
    status_counts: dict[str, int] = field(default_factory=dict)
    error_kind_counts: dict[str, int] = field(default_factory=dict)


def batch_report(batch_job_uid) -> BatchReport:
    """The latest attempt for each invitation the batch emailed.

    Latest overall, not latest from the batch: an email resent from the
    invitee page after the batch failed it is where that invitation stands.
    """
    uids = list(
        EmailDelivery.objects.filter(batch_job_uid=batch_job_uid).values_list("invitee_uid", flat=True).distinct()
    )
    report = BatchReport(by_invitee=latest_deliveries(uids))
    for row in report.by_invitee.values():
        status = delivery_status(row)
        report.status_counts[status] = report.status_counts.get(status, 0) + 1
        if status == EmailDelivery.Status.FAILED and row.error_kind:
            report.error_kind_counts[row.error_kind] = report.error_kind_counts.get(row.error_kind, 0) + 1
    return report


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
