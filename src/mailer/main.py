import json
import requests
import logging
from django.conf import settings

import os


logger = logging.getLogger(__name__)

MAILGUN_API_URL = settings.MAILGUN_API_URL
FROM_EMAIL_ADDRESS = "Jérôme Pinguet <noreply@mail.medica.im>"    # your domain, or Mailgun sandbox

AUTH = (settings.MAILGUN_SENDING_KEY_ID, settings.MAILGUN_SENDING_KEY )

def send_email_with_attachment(to_address: str, subject: str, message: str):
    try:
        files = {'attachment': open('./cover-letter.txt', 'rb')}   # file you want to attach
        # files = {'inline': open('./zen-attachment.jpg', 'rb')}   # file you want to attach

        resp = requests.post(MAILGUN_API_URL, auth=AUTH, files=files,
                             data={"from": FROM_EMAIL_ADDRESS,
                                   "to": to_address, "subject": subject, "html": message})
        if resp.status_code == 200:  # success
            logger.info(f"Successfully sent an email to '{to_address}' via Mailgun API.")
        else:   # error
            logging.error(f"Could not send the email, reason: {resp.text}")

    except Exception as ex:
        logging.exception(f"Mailgun error: {ex}")


def send_single_email(to_address: str, subject: str, message: str):
    try:
        resp = requests.post(MAILGUN_API_URL, auth=AUTH,
                     data={"from": FROM_EMAIL_ADDRESS,
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


def send_batch_emails(recipients: dict, subject: str, message: str) -> dict:
    try:
        to_address = list(recipients.keys())  # get only email addresses
        recipients_json = json.dumps(recipients)

        logger.info(f"Sending email to {len(to_address)} IDs...")
        resp = requests.post(MAILGUN_API_URL, auth=AUTH,
                             data={"from": FROM_EMAIL_ADDRESS,
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