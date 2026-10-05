"""A Mailgun call neither hangs nor gives up on a passing hiccup.

A batch of invitations is one Celery task posting one message per row
(access.tasks.process_batch_invitees). Two failure modes made that fragile:

* **No timeout.** requests.post without one waits forever on a server that
  stops answering, and the whole batch hung with it.
* **No retry.** A 429 (rate limit) or a 5xx from Mailgun marked that
  invitation failed; someone had to resend it by hand.

The rules, per call:

* every post carries a timeout;
* 429, 5xx and a connection that never got through are retried with a
  growing pause, honouring Mailgun's Retry-After on a 429;
* any other 4xx is final: a malformed address does not get better;
* a *read* timeout is final too: the request reached Mailgun, which may well
  have accepted it, and retrying would send the same invitation twice. Marked
  failed, it can be resent from the invitations page.

Every caller runs in a Celery task, so the pause never holds a web request.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from mailer.config import SenderConfig
from mailer.main import MAX_ATTEMPTS, send_batch_emails, send_single_email

SENDER = SenderConfig(
    api_url="https://api.eu.mailgun.net/v3/mail.example.org/messages",
    auth=("key-id", "key"),
    from_address="Example <contact@example.org>",
)


def _response(status, headers=None):
    response = MagicMock()
    response.status_code = status
    response.headers = headers or {}
    response.json.return_value = {"id": "<msg@example.org>"}
    response.text = f"status {status}"
    return response


def _send(*answers):
    """send_single_email against a scripted Mailgun; returns (result, post, sleep)."""
    with patch("mailer.main.requests.post", side_effect=list(answers)) as post, \
            patch("mailer.main.time.sleep") as sleep:
        result = send_single_email("who@example.org", "S", "t", sender=SENDER)
    return result, post, sleep


def test_every_post_carries_a_timeout():
    _, post, _ = _send(_response(200))
    assert post.call_args.kwargs.get("timeout")


def test_a_batch_post_carries_a_timeout_too():
    with patch("mailer.main.requests.post", return_value=_response(200)) as post, \
            patch("mailer.main.time.sleep"):
        send_batch_emails({"who@example.org": {}}, "S", "t", sender=SENDER)
    assert post.call_args.kwargs.get("timeout")


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_a_passing_error_is_retried_until_it_goes_through(status):
    result, post, sleep = _send(_response(status), _response(status), _response(200))
    assert result == {"id": "<msg@example.org>"}
    assert post.call_count == 3
    assert sleep.call_count == 2


def test_the_pause_grows_between_attempts():
    _, _, sleep = _send(_response(503), _response(503), _response(200))
    first, second = (call.args[0] for call in sleep.call_args_list)
    assert 0 < first < second


def test_a_rate_limit_says_how_long_to_wait():
    _, _, sleep = _send(_response(429, {"Retry-After": "7"}), _response(200))
    assert sleep.call_args.args[0] == 7


def test_an_absurd_retry_after_is_capped():
    """A worker parked for an hour on one header is a batch that looks hung."""
    _, _, sleep = _send(_response(429, {"Retry-After": "3600"}), _response(200))
    assert sleep.call_args.args[0] <= 60


def test_it_gives_up_after_the_last_attempt():
    result, post, _ = _send(*[_response(503)] * MAX_ATTEMPTS)
    assert post.call_count == MAX_ATTEMPTS
    assert result["status_code"] == 503
    assert "id" not in result


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_a_refusal_is_final(status):
    result, post, sleep = _send(_response(status))
    assert post.call_count == 1
    assert sleep.call_count == 0
    assert result["status_code"] == status


def test_a_connection_that_never_got_through_is_retried():
    result, post, _ = _send(requests.ConnectionError("refused"), _response(200))
    assert result == {"id": "<msg@example.org>"}
    assert post.call_count == 2


def test_a_connect_timeout_is_retried():
    result, post, _ = _send(requests.ConnectTimeout("no route"), _response(200))
    assert result == {"id": "<msg@example.org>"}
    assert post.call_count == 2


def test_a_read_timeout_is_not_retried():
    """Mailgun may have accepted it: a second post would mean a second email."""
    result, post, _ = _send(requests.ReadTimeout("slow"), _response(200))
    assert post.call_count == 1
    assert "error" in result


def test_a_batch_is_retried_like_a_single_email():
    with patch("mailer.main.requests.post", side_effect=[_response(503), _response(200)]) as post, \
            patch("mailer.main.time.sleep"):
        result = send_batch_emails({"who@example.org": {}}, "S", "t", sender=SENDER)
    assert result["success"] is True
    assert post.call_count == 2
