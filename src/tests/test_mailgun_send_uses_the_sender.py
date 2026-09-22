"""The Mailgun HTTP calls honour the sender they are given.

get_sender decides which identity an organization sends under; these tests
pin that mailer.main actually uses it -- the URL it posts to, the basic-auth
pair, and the From header -- instead of the module-level defaults it used
when every organization shared one address.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings

from mailer.config import SenderConfig
from mailer.main import send_batch_emails, send_single_email

ORG_SENDER = SenderConfig(
    api_url="https://api.eu.mailgun.net/v3/mail.example.org/messages",
    auth=("org-key-id", "org-key"),
    from_address="Cabinet Example <contact@example.org>",
)


def _ok_response():
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"id": "<msg@example.org>"}
    return response


def test_a_single_email_is_posted_under_the_given_sender():
    with patch("mailer.main.requests.post", return_value=_ok_response()) as post:
        send_single_email("who@example.org", "Subject", "Body", sender=ORG_SENDER)

    url = post.call_args.args[0]
    kwargs = post.call_args.kwargs
    assert url == ORG_SENDER.api_url
    assert kwargs["auth"] == ORG_SENDER.auth
    assert kwargs["data"]["from"] == ORG_SENDER.from_address


def test_a_batch_email_is_posted_under_the_given_sender():
    recipients = {"who@example.org": {"name": "Who", "uid": "u1"}}

    with patch("mailer.main.requests.post", return_value=_ok_response()) as post:
        send_batch_emails(recipients, "Subject", "Body", sender=ORG_SENDER)

    url = post.call_args.args[0]
    kwargs = post.call_args.kwargs
    assert url == ORG_SENDER.api_url
    assert kwargs["auth"] == ORG_SENDER.auth
    assert kwargs["data"]["from"] == ORG_SENDER.from_address


def test_without_a_sender_the_env_identity_is_used():
    """Callers that have no organization in hand keep working unchanged."""
    with patch("mailer.main.requests.post", return_value=_ok_response()) as post:
        send_single_email("who@example.org", "Subject", "Body")

    assert post.call_args.args[0] == settings.MAILGUN_API_URL
    assert post.call_args.kwargs["auth"] == (
        settings.MAILGUN_SENDING_KEY_ID,
        settings.MAILGUN_SENDING_KEY,
    )
    assert post.call_args.kwargs["data"]["from"] == settings.MAILGUN_FROM_ADDRESS
