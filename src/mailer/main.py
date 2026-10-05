"""Sending mail, in the app's terms; the provider does the talking.

send_single_email and send_batch_emails keep the dict answers their callers
(mailer.tasks, access.tasks, mailer.delivery) already read; underneath they
build an OutgoingMessage and get a SendOutcome back from the provider
(mailer/providers). Nothing here may know the provider's wire format: see
tests/test_mail_provider_boundary.py.
"""
import logging

from mailer.config import SenderConfig
from mailer.providers import get_provider
from mailer.providers.base import OutgoingMessage, SendOutcome

logger = logging.getLogger(__name__)


def _resolve(sender: SenderConfig | None) -> SenderConfig:
    """Callers with no organization in hand send under the deployment's identity."""
    return sender if sender is not None else SenderConfig.default()


def _send(sender: SenderConfig, **fields) -> SendOutcome:
    message = OutgoingMessage(from_address=sender.from_address, reply_to=sender.reply_to, **fields)
    return get_provider().send(message, sender.credentials)


def send_single_email(
    to_address: str,
    subject: str,
    message: str,
    sender: SenderConfig | None = None,
    *,
    html: str | None = None,
) -> dict:
    """{"id": ...} when accepted; {"error": ..., "status_code"?, "error_kind"} otherwise."""
    outcome = _send(_resolve(sender), to=to_address, subject=subject, text=message, html=html)
    if outcome.accepted:
        logger.info(f"Email to '{to_address}' accepted: {outcome.message_id}")
        return outcome.raw if isinstance(outcome.raw, dict) else {"id": outcome.message_id}
    logger.error(f"Email to '{to_address}' not accepted ({outcome.error_kind}): {outcome.status_code} {outcome.detail}")
    result = {"error": outcome.detail, "error_kind": str(outcome.error_kind)}
    if outcome.status_code is not None:
        result["status_code"] = outcome.status_code
    return result


def send_batch_emails(
    recipients: dict,
    subject: str,
    message: str,
    sender: SenderConfig | None = None,
    *,
    html: str | None = None,
) -> dict:
    """One message, an individual copy to each of `recipients` (address -> data)."""
    logger.info(f"Sending email to {len(recipients)} recipients...")
    outcome = _send(
        _resolve(sender), to=list(recipients.keys()), subject=subject, text=message, html=html,
        per_recipient=recipients,
    )
    if outcome.accepted:
        logger.info(f"Email to {len(recipients)} recipients accepted.")
        return {"success": True, "status_code": outcome.status_code, "response": outcome.raw}
    logger.error(f"Email to {len(recipients)} recipients not accepted ({outcome.error_kind}): {outcome.detail}")
    return {"success": False, "status_code": outcome.status_code, "response": outcome.detail}
