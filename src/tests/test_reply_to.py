"""Replies to an organization's email reach the organization.

Mail goes out From a sending domain the organization does not own --
`CPTS Opale Sud <noreply@mail.medica.im>`, since nobody here has access to
cptsopalesud.fr's DNS -- so without a Reply-To, a professional answering an
invitation wrote to a mailbox nobody reads.

Organization.reply_to_email says where replies go. It sits on the
organization, not on MailgunAccount: where a reply should land is a fact about
the organization, whichever service sends the mail. Unset, replies go to
settings.MAIL_DEFAULT_REPLY_TO, `noreply@<MAILGUN_DOMAIN>` unless the .env says
otherwise.

SenderConfig carries the address; only the Mailgun call knows it becomes an
`h:Reply-To` field.
"""
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings

from mailer.config import SenderConfig, get_sender
from mailer.main import send_batch_emails, send_single_email
from mailer.models import MailgunAccount


class FakeOrganization:
    def __init__(self, reply_to_email="", mailgun_account=None):
        self.reply_to_email = reply_to_email
        self._mailgun_account = mailgun_account

    @property
    def mailgun_account(self):
        if self._mailgun_account is None:
            raise AttributeError("no mailgun_account")
        return self._mailgun_account


def make_account():
    return MailgunAccount(
        api_key="k", sending_key_id="kid", domain="mail.example.org", region="eu",
        from_email="contact@example.org", from_name="Cabinet Example", active=True,
    )


def _ok():
    response = MagicMock()
    response.status_code = 200
    response.headers = {}
    response.json.return_value = {"id": "<m@example.org>"}
    return response


class TestWhereRepliesGo:
    def test_the_default_is_noreply_at_the_default_sending_domain(self):
        assert settings.MAIL_DEFAULT_REPLY_TO == f"noreply@{settings.MAILGUN_DOMAIN}"
        assert SenderConfig.default().reply_to == settings.MAIL_DEFAULT_REPLY_TO

    def test_without_a_sender_the_default_applies(self):
        assert get_sender(None).reply_to == settings.MAIL_DEFAULT_REPLY_TO

    def test_an_organization_without_an_address_gets_the_default(self):
        assert get_sender(FakeOrganization()).reply_to == settings.MAIL_DEFAULT_REPLY_TO

    def test_an_organization_sending_under_the_default_account_still_gets_its_own(self):
        """The common case: no MailgunAccount, but replies must reach it."""
        sender = get_sender(FakeOrganization("secretariat@cpts.example"))
        assert sender.reply_to == "secretariat@cpts.example"
        assert sender.from_address == SenderConfig.default().from_address

    def test_an_organization_with_its_own_account_gets_its_own(self):
        sender = get_sender(FakeOrganization("secretariat@cpts.example", make_account()))
        assert sender.reply_to == "secretariat@cpts.example"
        assert sender.from_address == "Cabinet Example <contact@example.org>"


class TestTheMessageCarriesIt:
    SENDER = SenderConfig(
        api_url="https://api.eu.mailgun.net/v3/mail.example.org/messages",
        auth=("kid", "k"),
        from_address="Example <contact@example.org>",
        reply_to="secretariat@cpts.example",
    )

    def test_a_single_email(self):
        with patch("mailer.main.requests.post", return_value=_ok()) as post:
            send_single_email("who@example.org", "S", "t", sender=self.SENDER)
        assert post.call_args.kwargs["data"]["h:Reply-To"] == "secretariat@cpts.example"

    def test_a_batch_email(self):
        with patch("mailer.main.requests.post", return_value=_ok()) as post:
            send_batch_emails({"who@example.org": {}}, "S", "t", sender=self.SENDER)
        assert post.call_args.kwargs["data"]["h:Reply-To"] == "secretariat@cpts.example"

    def test_the_default_sender_sets_it_too(self):
        with patch("mailer.main.requests.post", return_value=_ok()) as post:
            send_single_email("who@example.org", "S", "t")
        assert post.call_args.kwargs["data"]["h:Reply-To"] == settings.MAIL_DEFAULT_REPLY_TO


@pytest.mark.django_db
def test_the_address_is_an_organization_field(site):
    from facility.models import Organization

    organization = Organization.objects.create(name="reply-to-org", site=site, reply_to_email="secretariat@cpts.example")
    assert get_sender(organization).reply_to == "secretariat@cpts.example"
