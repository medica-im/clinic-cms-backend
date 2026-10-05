"""What the app says about mail, whatever service carries it.

An OutgoingMessage is what to send; a SendOutcome is how the attempt went, its
failure named by an ErrorKind. A provider (providers/mailgun.py) turns one
into the other. Nothing here may import a provider or speak its wire format:
tests/test_mail_provider_boundary.py checks it.
"""
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class ErrorKind(StrEnum):
    """Why a message was not accepted, in terms a report can act on."""

    # Refused as written: an address the service rejects, a malformed field.
    # Sending it again unchanged will fail again.
    INVALID_REQUEST = "invalid_request"
    # Our side is wrong: credentials, sending domain. Every message will fail
    # until someone fixes the configuration.
    MISCONFIGURED = "misconfigured"
    # Too many messages too fast, still so after the retries.
    RATE_LIMITED = "rate_limited"
    # The service answered that it is failing, still so after the retries.
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    # The service could not be reached at all: nothing was sent.
    UNREACHABLE = "unreachable"
    # The request went out and no answer came back: it may have been
    # accepted. Retrying blindly could send it twice.
    OUTCOME_UNKNOWN = "outcome_unknown"


@dataclass(frozen=True)
class OutgoingMessage:
    to: str | list[str]
    subject: str
    text: str
    from_address: str
    html: str | None = None
    reply_to: str = ""
    # Several recipients, each receiving their own copy and seeing only
    # themselves; values are per-recipient data. None: one message to `to`.
    per_recipient: dict[str, dict] | None = None


@dataclass(frozen=True)
class SendOutcome:
    accepted: bool
    message_id: str = ""
    error_kind: ErrorKind | None = None
    detail: str = ""
    # The service's HTTP status when there was one, for the record.
    status_code: int | None = None
    # The service's answer as received, for logs and stored records only:
    # never branch on it outside the provider.
    raw: Any = field(default=None, compare=True)


class MailProvider(Protocol):
    """A mail service. Credentials are the provider's own, opaque elsewhere."""

    def default_identity(self) -> tuple[Any, str]:
        """(credentials, from address) of the deployment's own account."""

    def identity_for(self, organization) -> tuple[Any, str] | None:
        """The organization's own (credentials, from address), or None."""

    def send(self, message: OutgoingMessage, credentials) -> SendOutcome: ...
