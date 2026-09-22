import json
import logging

import requests

from mailer.config import SenderConfig

logger = logging.getLogger(__name__)


def _resolve(sender: SenderConfig | None) -> SenderConfig:
    """Callers with no organization in hand send under the .env identity."""
    return sender if sender is not None else SenderConfig.default()


def send_email_with_attachment(
    to_address: str,
    subject: str,
    message: str,
    sender: SenderConfig | None = None,
):
    sender = _resolve(sender)
    try:
        files = {'attachment': open('./cover-letter.txt', 'rb')}   # file you want to attach
        # files = {'inline': open('./zen-attachment.jpg', 'rb')}   # file you want to attach

        resp = requests.post(sender.api_url, auth=sender.auth, files=files,
                             data={"from": sender.from_address,
                                   "to": to_address, "subject": subject, "html": message})
        if resp.status_code == 200:  # success
            logger.info(f"Successfully sent an email to '{to_address}' via Mailgun API.")
        else:   # error
            logging.error(f"Could not send the email, reason: {resp.text}")

    except Exception as ex:
        logging.exception(f"Mailgun error: {ex}")


def send_single_email(
    to_address: str,
    subject: str,
    message: str,
    sender: SenderConfig | None = None,
):
    sender = _resolve(sender)
    try:
        resp = requests.post(sender.api_url, auth=sender.auth,
                     data={"from": sender.from_address,
                           "to": to_address, "subject": subject, "text": message})
        if resp.status_code == 200:  # success
            result = resp.json()
            logger.info(f"Successfully sent an email to '{to_address}' via Mailgun API. Response: {result}")
            return result
        else:   # error
            logger.error(f"Could not send the email: {resp.status_code} {resp.text}")
            return {"error": resp.text, "status_code": resp.status_code}

    except Exception as ex:
        logger.exception(f"Mailgun error: {ex}")
        return {"error": str(ex)}


def send_batch_emails(
    recipients: dict,
    subject: str,
    message: str,
    sender: SenderConfig | None = None,
) -> dict:
    sender = _resolve(sender)
    try:
        to_address = list(recipients.keys())  # get only email addresses
        recipients_json = json.dumps(recipients)

        logger.info(f"Sending email to {len(to_address)} IDs...")
        resp = requests.post(sender.api_url, auth=sender.auth,
                             data={"from": sender.from_address,
                                   "to": to_address, "subject": subject, "text": message,
                                   "recipient-variables": recipients_json})
        if resp.status_code == 200:  # success
            logger.info(f"Successfully sent email to {len(recipients)} recipients via Mailgun API.")
            return {"success": True, "status_code": resp.status_code, "response": resp.json()}
        else:   # error
            logger.error(f"Could not send emails, reason: {resp.text}")
            return {"success": False, "status_code": resp.status_code, "response": resp.text}
    except Exception as ex:
        logger.exception(f"Mailgun error: {ex}")
        return {"success": False, "status_code": None, "response": str(ex)}
