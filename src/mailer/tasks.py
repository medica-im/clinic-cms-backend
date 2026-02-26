import logging
from celery import shared_task
from mailer.main import send_single_email

logger = logging.getLogger(__name__)


@shared_task
def send_single_email_task(to_address, subject, message):
    logger.info(f"Sending email to {to_address}")
    res = send_single_email(to_address, subject, message)
    return res