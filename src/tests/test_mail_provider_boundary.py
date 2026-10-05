"""Only one file knows Mailgun.

The app says *what* to send -- an OutgoingMessage, from a sender identity --
and reads back *how it went* -- a SendOutcome with an ErrorKind. How a
message becomes Mailgun form fields (`h:Reply-To`, `recipient-variables`),
which URL it is posted to, and what a 401 or a 429 from Mailgun means, live in
mailer/providers/mailgun.py and nowhere else.

The point is the day mail goes through another service: that should be one
new providers/<name>.py and a setting, not a rewrite of the delivery records,
the batch task and the reports. The source checks below are what keeps that
true; a component test per caller would miss the next caller.
"""
import ast
import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from mailer.providers import get_provider
from mailer.providers.base import ErrorKind, OutgoingMessage, SendOutcome
from mailer.providers.mailgun import MailgunCredentials, MailgunProvider

SRC = Path(__file__).resolve().parents[1]

# Code that sends or settles mail without needing to know the service.
NEUTRAL = [
    "mailer/main.py",
    "mailer/config.py",
    "mailer/delivery.py",
    "mailer/tasks.py",
    "mailer/providers/base.py",
    "mailer/providers/__init__.py",
    "access/tasks.py",
]

# What would mean Mailgun leaked: its wire format, its hosts, a raw HTTP call.
LEAKS = ["h:Reply-To", "recipient-variables", "o:tag", "api.mailgun", "api.eu.mailgun", "requests.post"]


@pytest.mark.parametrize("path", NEUTRAL)
def test_neutral_code_speaks_no_mailgun(path):
    source = (SRC / path).read_text()
    found = [leak for leak in LEAKS if leak in source]
    assert found == [], f"{path} knows Mailgun's wire format: {found}; move it to mailer/providers/mailgun.py"


def test_the_vocabulary_imports_no_provider():
    tree = ast.parse((SRC / "mailer/providers/base.py").read_text())
    imported = {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    } | {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert not any("mailgun" in name or name == "requests" for name in imported), imported


class TestChoosingTheProvider:
    def test_mailgun_by_default(self):
        assert isinstance(get_provider(), MailgunProvider)

    @override_settings(MAIL_PROVIDER="carrier-pigeon")
    def test_an_unknown_one_is_a_configuration_error(self):
        with pytest.raises(ImproperlyConfigured):
            get_provider()


CREDENTIALS = MailgunCredentials(
    api_url="https://api.eu.mailgun.net/v3/mail.example.org/messages", auth=("kid", "k"),
)


def _response(status, body=None, headers=None):
    response = MagicMock()
    response.status_code = status
    response.headers = headers or {}
    response.json.return_value = body if body is not None else {"id": "<m@example.org>", "message": "Queued"}
    response.text = f"status {status}"
    return response


def _send(*answers, message=None):
    message = message or OutgoingMessage(
        to="who@example.org", subject="S", text="t", from_address="Org <noreply@example.org>",
    )
    with patch("mailer.providers.mailgun.requests.post", side_effect=list(answers)) as post, \
            patch("mailer.providers.mailgun.time.sleep"):
        outcome = MailgunProvider().send(message, CREDENTIALS)
    return outcome, post


class TestWhatMailgunIsSent:
    def test_the_fields(self):
        message = OutgoingMessage(
            to="who@example.org", subject="S", text="t", html="<p>t</p>",
            from_address="Org <noreply@example.org>", reply_to="org@example.org",
        )
        _, post = _send(_response(200), message=message)
        assert post.call_args.args[0] == CREDENTIALS.api_url
        assert post.call_args.kwargs["auth"] == CREDENTIALS.auth
        assert post.call_args.kwargs["data"] == {
            "from": "Org <noreply@example.org>", "to": "who@example.org", "subject": "S",
            "text": "t", "html": "<p>t</p>", "h:Reply-To": "org@example.org",
        }

    def test_individual_copies_to_several(self):
        """Each recipient sees only themselves: Mailgun's recipient-variables."""
        per_recipient = {"a@example.org": {"uid": "1"}, "b@example.org": {"uid": "2"}}
        message = OutgoingMessage(
            to=list(per_recipient), subject="S", text="t", from_address="o@example.org",
            per_recipient=per_recipient,
        )
        _, post = _send(_response(200), message=message)
        data = post.call_args.kwargs["data"]
        assert data["to"] == ["a@example.org", "b@example.org"]
        assert "recipient-variables" in data


class TestWhatTheAnswerMeans:
    def test_accepted(self):
        outcome, _ = _send(_response(200))
        assert outcome == SendOutcome(
            accepted=True, message_id="<m@example.org>", status_code=200,
            raw={"id": "<m@example.org>", "message": "Queued"},
        )

    @pytest.mark.parametrize("status,kind", [
        (400, ErrorKind.INVALID_REQUEST),
        (401, ErrorKind.MISCONFIGURED),
        (403, ErrorKind.MISCONFIGURED),
        (404, ErrorKind.MISCONFIGURED),
    ])
    def test_a_refusal(self, status, kind):
        outcome, _ = _send(_response(status))
        assert not outcome.accepted
        assert outcome.error_kind == kind
        assert outcome.status_code == status

    def test_still_rate_limited_after_every_retry(self):
        outcome, _ = _send(*[_response(429)] * 4)
        assert outcome.error_kind == ErrorKind.RATE_LIMITED

    def test_still_down_after_every_retry(self):
        outcome, _ = _send(*[_response(503)] * 4)
        assert outcome.error_kind == ErrorKind.PROVIDER_UNAVAILABLE

    def test_never_reached(self):
        outcome, _ = _send(*[requests.ConnectionError("refused")] * 4)
        assert outcome.error_kind == ErrorKind.UNREACHABLE

    def test_no_answer_in_time(self):
        """Sent, maybe accepted: say so rather than guess either way."""
        outcome, _ = _send(requests.ReadTimeout("slow"))
        assert outcome.error_kind == ErrorKind.OUTCOME_UNKNOWN
