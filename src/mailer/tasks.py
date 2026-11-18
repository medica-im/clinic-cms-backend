import logging
from time import time_ns
from celery import shared_task

from facility.models import Organization
from mailer.config import get_sender
from mailer.delivery import mark_result, mark_suppressed
from mailer.main import send_single_email, send_batch_emails

logger = logging.getLogger(__name__)


def _organization(organization_id):
    if organization_id is None:
        return None
    try:
        return Organization.objects.get(id=organization_id)
    except Organization.DoesNotExist:
        logger.error(f"Organization {organization_id} not found; sending with the default credentials")
        return None


def _sender_for(organization_id):
    """Resolve the sending identity inside the worker.

    The task is given an id rather than a resolved sender: a SenderConfig is
    not JSON-serialisable, and resolving here also picks up a credential
    change made between queueing and sending.
    """
    return get_sender(_organization(organization_id))


@shared_task
def send_single_email_task(
    to_address, subject, message, organization_id=None, html=None, delivery_id=None, force_send=False,
):
    """delivery_id: the invitation's EmailDelivery row, settled with the
    service's answer and sent along so its later events find it.

    An invitation to a remembered address (mailer.suppression: dead, or a
    refusal of this organization's mail) is not sent but marked suppressed --
    unless force_send, an administrator's resend after checking a dead
    address (never a refusal: the resend endpoint does not allow it)."""
    from mailer import suppression

    tracked = delivery_id is not None
    organization = _organization(organization_id)
    if tracked and not force_send:
        blocked = suppression.blocking(to_address, organization)
        if blocked is not None:
            logger.info(f"Not sending to {to_address}: {blocked.reason}")
            mark_suppressed(delivery_id, blocked)
            return {"suppressed": blocked.reason}
    logger.info(f"Sending email to {to_address}")
    res = send_single_email(
        to_address, subject, message, sender=get_sender(organization), html=html,
        metadata={"delivery_id": delivery_id} if tracked else None,
        tags=["invitation"] if tracked else None,
    )
    if tracked:
        mark_result(delivery_id, res)
    return res


@shared_task
def send_batch_emails_task(
    recipients, subject, message, author_uid, recipient_uids, organization_id=None
):
    logger.info(f"send_batch_emails_task called with {len(recipients)} recipients, author={author_uid}")
    logger.debug(f"recipients: {recipients}")
    logger.debug(f"recipient_uids: {recipient_uids}")

    try:
        result = send_batch_emails(
            recipients, subject, message, sender=_sender_for(organization_id)
        )
        logger.info(f"Mailgun result: {result}")
    except Exception as e:
        logger.exception(f"send_batch_emails raised an exception: {e}")
        result = {"success": False, "status_code": None, "response": str(e)}

    sent_at = time_ns() // 1_000_000

    try:
        from mailer.models import BatchEmailMessage
        BatchEmailMessage.objects.create(
            author_uid=author_uid,
            subject=subject,
            body=message,
            sent_at=sent_at,
            recipient_uids=recipient_uids,
            mailgun_response=result,
            success=result.get("success", False),
        )
        logger.info(f"BatchEmailMessage archived successfully")
    except Exception as e:
        logger.exception(f"Failed to archive BatchEmailMessage: {e}")

    return result
