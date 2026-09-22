"""Each organization may send email under its own Mailgun identity.

The invitation system used to send every organization's mail from one
hardcoded address with the credentials in the .env file. Recipients of an
invitation from organization A saw organization B's From address, and a
bounce or a spam complaint landed on the wrong domain's reputation.

An organization now optionally owns a MailgunAccount row (managed in the
Django admin). When it has an active one, its mail goes out with those
credentials and that From address. When it has none -- the common case --
it falls back to the credentials in the .env file, so nothing has to be
configured for an organization to keep working.
"""

import pytest
from django.conf import settings

from mailer.config import SenderConfig, get_sender
from mailer.models import MailgunAccount


def make_account(**overrides):
    """An unsaved MailgunAccount row, so the real usability rule is exercised."""
    fields = {
        "api_key": "org-key",
        "sending_key_id": "org-key-id",
        "domain": "mail.example.org",
        "region": "eu",
        "from_email": "contact@example.org",
        "from_name": "Cabinet Example",
        "active": True,
    }
    fields.update(overrides)
    return MailgunAccount(**fields)


class FakeOrganization:
    def __init__(self, mailgun_account=None):
        self._mailgun_account = mailgun_account

    @property
    def mailgun_account(self):
        if self._mailgun_account is None:
            raise AttributeError("no mailgun_account")
        return self._mailgun_account


def test_organization_with_an_account_sends_under_its_own_identity():
    account = make_account()
    sender = get_sender(FakeOrganization(account))

    assert sender.auth == ("org-key-id", "org-key")
    assert sender.from_address == "Cabinet Example <contact@example.org>"
    assert sender.api_url == "https://api.eu.mailgun.net/v3/mail.example.org/messages"


def test_an_account_without_a_from_name_sends_the_bare_address():
    account = make_account(from_name="")
    sender = get_sender(FakeOrganization(account))

    assert sender.from_address == "contact@example.org"


def test_the_region_selects_the_mailgun_endpoint():
    account = make_account(region="us")
    sender = get_sender(FakeOrganization(account))

    assert sender.api_url == "https://api.mailgun.net/v3/mail.example.org/messages"


def test_an_organization_without_an_account_falls_back_to_the_env_credentials():
    sender = get_sender(FakeOrganization(None))

    assert sender.auth == (
        settings.MAILGUN_SENDING_KEY_ID,
        settings.MAILGUN_SENDING_KEY,
    )
    assert sender.api_url == settings.MAILGUN_API_URL
    assert sender.from_address == settings.MAILGUN_FROM_ADDRESS


def test_an_inactive_account_falls_back_to_the_env_credentials():
    account = make_account(active=False)
    sender = get_sender(FakeOrganization(account))

    assert sender.auth == (
        settings.MAILGUN_SENDING_KEY_ID,
        settings.MAILGUN_SENDING_KEY,
    )
    assert sender.from_address == settings.MAILGUN_FROM_ADDRESS


def test_an_incomplete_account_falls_back_rather_than_sending_with_half_credentials():
    """A half-filled row must not produce a 401 from Mailgun at send time."""
    account = make_account(api_key="")
    sender = get_sender(FakeOrganization(account))

    assert sender.auth == (
        settings.MAILGUN_SENDING_KEY_ID,
        settings.MAILGUN_SENDING_KEY,
    )


def test_no_organization_at_all_falls_back_to_the_env_credentials():
    sender = get_sender(None)

    assert sender.api_url == settings.MAILGUN_API_URL
    assert isinstance(sender, SenderConfig)
