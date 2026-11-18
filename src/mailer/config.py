"""Which identity an organization's mail goes out under.

One address for every organization meant a recipient invited by A saw B's
From address, and a bounce landed on the wrong domain's reputation. An
organization may now have its own account with the mail provider; when it
does not, it sends under the deployment's own account (.env), so nothing needs
configuring for an organization to keep working.

The identity is provider-neutral: From, Reply-To, and credentials that only
the provider reads (mailer/providers).
"""

import logging
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from mailer.providers import get_provider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SenderConfig:
    """Who a message is from, where replies go, and what to send it with."""

    from_address: str
    # Where replies go; the provider maps it to its own field.
    reply_to: str = ""
    # The provider's own credentials (MailgunCredentials, ...). Opaque here.
    credentials: Any = None

    @classmethod
    def default(cls) -> "SenderConfig":
        """The deployment's own identity, for every organization without an account."""
        credentials, from_address = get_provider().default_identity()
        return cls(from_address=from_address, reply_to=settings.MAIL_DEFAULT_REPLY_TO, credentials=credentials)


def get_sender(organization) -> SenderConfig:
    """The identity to send this organization's mail under, replies to it.

    Its own provider account when it has a usable one, the deployment's
    otherwise; its own reply address when it has set one, the default
    otherwise -- the two are independent.
    """
    own = get_provider().identity_for(organization)
    if own is None:
        credentials, from_address = get_provider().default_identity()
    else:
        credentials, from_address = own
    reply_to = getattr(organization, "reply_to_email", "") or settings.MAIL_DEFAULT_REPLY_TO
    return SenderConfig(from_address=from_address, reply_to=reply_to, credentials=credentials)
