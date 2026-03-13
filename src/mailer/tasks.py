import logging
from time import time_ns
from celery import shared_task
from mailer.main import send_single_email, send_batch_emails

logger = logging.getLogger(__name__)


@shared_task
def send_single_email_task(to_address, subject, message):
    logger.info(f"Sending email to {to_address}")
    res = send_single_email(to_address, subject, message)
    return res


@shared_task
def send_batch_emails_task(recipients, subject, message, author_uid, recipient_uids):
    logger.info(f"send_batch_emails_task called with {len(recipients)} recipients, author={author_uid}")
    logger.debug(f"recipients: {recipients}")
    logger.debug(f"recipient_uids: {recipient_uids}")

    try:
        result = send_batch_emails(recipients, subject, message)
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
