import json
import logging
import time

import requests

from mailer.config import SenderConfig

logger = logging.getLogger(__name__)

# (connect, read) seconds. Without one, a Mailgun that stops answering held
# the batch invitation task forever.
TIMEOUT = (5, 30)
MAX_ATTEMPTS = 4
BACKOFF = 2  # seconds before the 2nd attempt, doubled each time after
MAX_PAUSE = 60  # cap on Retry-After, so one header cannot park the worker


def _retryable(status: int) -> bool:
    return status == 429 or status >= 500


def _pause(attempt: int, response=None) -> float:
    retry_after = (response.headers or {}).get("Retry-After") if response is not None else None
    if retry_after:
        try:
            return min(float(retry_after), MAX_PAUSE)
        except ValueError:
            pass
    return min(BACKOFF * 2 ** (attempt - 1), MAX_PAUSE)


def _post(sender: SenderConfig, **kwargs) -> requests.Response:
    """POST to Mailgun with a timeout, retrying what may pass.

    Retried: 429, 5xx, and a connection that never got through. Final: any
    other answer, and a read timeout -- the request reached Mailgun, which may
    have accepted it, and a second post would send the email twice. Raises
    the last connection error when every attempt failed to connect. Callers
    all run in Celery tasks, so the pause holds no web request.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.post(sender.api_url, auth=sender.auth, timeout=TIMEOUT, **kwargs)
        except (requests.ConnectionError, requests.ConnectTimeout) as e:
            if isinstance(e, requests.ReadTimeout) or attempt == MAX_ATTEMPTS:
                raise
            logger.warning(f"Mailgun unreachable (attempt {attempt}/{MAX_ATTEMPTS}): {e}")
            time.sleep(_pause(attempt))
            continue
        if not _retryable(response.status_code) or attempt == MAX_ATTEMPTS:
            return response
        logger.warning(f"Mailgun answered {response.status_code} (attempt {attempt}/{MAX_ATTEMPTS}), retrying")
        time.sleep(_pause(attempt, response))
    raise AssertionError("unreachable")


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


def _message_data(sender: SenderConfig, to, subject: str, text: str, html: str | None) -> dict:
    """Mailgun form fields. The html part is only added when there is one, so
    a text email posts exactly the fields it always did."""
    data = {"from": sender.from_address, "to": to, "subject": subject, "text": text}
    if html is not None:
        data["html"] = html
    if sender.reply_to:
        data["h:Reply-To"] = sender.reply_to
    return data


def send_single_email(
    to_address: str,
    subject: str,
    message: str,
    sender: SenderConfig | None = None,
    *,
    html: str | None = None,
):
    sender = _resolve(sender)
    try:
        resp = _post(sender, data=_message_data(sender, to_address, subject, message, html))
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
    *,
    html: str | None = None,
) -> dict:
    sender = _resolve(sender)
    try:
        to_address = list(recipients.keys())  # get only email addresses
        recipients_json = json.dumps(recipients)

        logger.info(f"Sending email to {len(to_address)} IDs...")
        resp = _post(sender, data={**_message_data(sender, to_address, subject, message, html),
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
