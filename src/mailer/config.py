"""Resolving which Mailgun identity an organization's mail goes out under.

One address for every organization meant a recipient invited by A saw B's
From address, and a bounce landed on the wrong domain's reputation. An
organization may now own a MailgunAccount row; when it does not, it sends
under the credentials in the .env file, so nothing needs configuring for an
organization to keep working.
"""

import logging
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from mailer.endpoints import build_api_url

logger = logging.getLogger(__name__)


def format_from_address(email: str, name: str = "") -> str:
    return f"{name} <{email}>" if name else email


@dataclass(frozen=True)
class SenderConfig:
    """Everything mailer.main needs to post one message to Mailgun."""

    api_url: str
    auth: tuple[str, str]
    from_address: str

    @classmethod
    def default(cls) -> "SenderConfig":
        """The .env identity, used by every organization without an account."""
        return cls(
            api_url=settings.MAILGUN_API_URL,
            auth=(settings.MAILGUN_SENDING_KEY_ID, settings.MAILGUN_SENDING_KEY),
            from_address=settings.MAILGUN_FROM_ADDRESS,
        )


def get_sender(organization) -> SenderConfig:
    """The Mailgun identity to send this organization's mail under.

    Falls back to the default identity when the organization is unknown, has
    no account, or has one that is inactive or half-filled. A half-filled row
    must not reach Mailgun: it would fail with a 401 at send time, which is
    far harder to diagnose than mail arriving from the default address.
    """
    if organization is None:
        return SenderConfig.default()

    try:
        account = organization.mailgun_account
    except (AttributeError, ObjectDoesNotExist):
        return SenderConfig.default()

    if account is None or not account.is_usable():
        logger.info(
            f"Mailgun account for organization {organization} is unusable; "
            f"falling back to the default credentials"
        )
        return SenderConfig.default()

    return SenderConfig(
        api_url=build_api_url(account.domain, account.region),
        auth=(account.sending_key_id, account.api_key),
        from_address=format_from_address(account.from_email, account.from_name),
    )
