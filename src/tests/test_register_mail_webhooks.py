"""Pointing a sending domain's webhooks at this backend, from the command line.

    manage.py register_mail_webhooks --url https://dev.medica.im/api/v2/mail/events/mailgun

A webhook belongs to a sending domain, and a domain's webhook reaches one
URL. Several backends share mail.medica.im today, so registering dev's URL
on it would quietly divert production's events to dev -- every bounce of a
real invitation lost. The command therefore never moves a webhook that
already points elsewhere unless told to (--replace), and says where it points.

The provider does the talking (Mailgun's /v3/domains/<domain>/webhooks); the
command only says which events matter and where they go.
"""
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

URL = "https://dev.medica.im/api/v2/mail/events/mailgun"
ELSEWHERE = "https://production.medica.im/api/v2/mail/events/mailgun"


def answer(status, body=None):
    response = MagicMock(status_code=status)
    response.json.return_value = body or {}
    response.text = str(body)
    return response


def existing(url):
    return answer(200, {"webhook": {"urls": [url]}})


def run(gets, *args):
    """gets: Mailgun's answer to the lookup of each webhook, in order."""
    out = StringIO()
    with patch("mailer.providers.mailgun.requests.get", side_effect=gets) as get, \
            patch("mailer.providers.mailgun.requests.post", return_value=answer(200)) as post, \
            patch("mailer.providers.mailgun.requests.put", return_value=answer(200)) as put:
        call_command("register_mail_webhooks", "--url", URL, "--domain", "mail-dev.medica.im", *args, stdout=out)
    return out.getvalue(), get, post, put


EVENTS = 5  # delivered, permanent_fail, temporary_fail, complained, unsubscribed


def test_missing_webhooks_are_created():
    _, _, post, put = run([answer(404)] * EVENTS)
    assert post.call_count == EVENTS
    assert put.call_count == 0
    assert all(call.kwargs["data"]["url"] == URL for call in post.call_args_list)
    assert {call.kwargs["data"]["id"] for call in post.call_args_list} == {
        "delivered", "permanent_fail", "temporary_fail", "complained", "unsubscribed",
    }


def test_webhooks_already_here_are_left_alone():
    out, _, post, put = run([existing(URL)] * EVENTS)
    assert post.call_count == put.call_count == 0
    assert "already" in out


def test_a_webhook_pointing_elsewhere_is_not_moved():
    with pytest.raises(CommandError) as refused:
        run([existing(ELSEWHERE)] + [answer(404)] * (EVENTS - 1))
    assert ELSEWHERE in str(refused.value)


def test_unless_told_to():
    _, _, _, put = run([existing(ELSEWHERE)] + [answer(404)] * (EVENTS - 1), "--replace")
    assert put.call_count == 1
    assert put.call_args.kwargs["data"]["url"] == URL


def test_a_dry_run_changes_nothing():
    out, _, post, put = run([answer(404)] * EVENTS, "--dry-run")
    assert post.call_count == put.call_count == 0
    assert "would create" in out


def test_the_account_api_key_comes_from_the_env():
    """Managing webhooks needs an account API key; a sending key may lack the rights."""
    from django.conf import settings
    from django.test import override_settings

    assert hasattr(settings, "MAILGUN_API_KEY"), "settings.py must read MAILGUN_API_KEY from .env"
    with override_settings(MAILGUN_API_KEY="account-key"):
        _, get, _, _ = run([answer(404)] * EVENTS, "--dry-run")
    assert get.call_args.kwargs["auth"] == ("api", "account-key")


def test_without_one_the_sending_key_is_tried():
    from django.conf import settings
    from django.test import override_settings

    with override_settings(MAILGUN_API_KEY=""):
        _, get, _, _ = run([answer(404)] * EVENTS, "--dry-run")
    assert get.call_args.kwargs["auth"] == ("api", settings.MAILGUN_SENDING_KEY)
