"""Django's own mail goes out through Mailgun, like everything else.

Django sends mail itself in one place here: the error reports to ADMINS
(AdminEmailHandler, when DEBUG is off) -- how a server error reaches anyone.
It used to be configured for SMTP and then overridden in the .env with an
anymail backend that had no ANYMAIL settings, so it could not have sent
anything; the SMTP block, read without defaults, could not even be removed
from the .env without breaking startup.

Now Django mail uses django-anymail's Mailgun backend, configured from the
same MAILGUN_* settings as the app's own mail -- one domain, one key, no
second set of credentials -- and From the same address.

It must fail fast: error reports are sent synchronously inside the failing
request, and on 13 Sep 2026 a hanging mail connection turned one erroring
endpoint into a total outage. So anymail's timeout is EMAIL_TIMEOUT.
"""
import inspect
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.core import mail
from django.test import override_settings

import backend.settings as settings_module


# pytest-django swaps EMAIL_BACKEND for its in-memory one during tests, so
# the configured value is read from the settings module itself.
MAILGUN_BACKEND = "anymail.backends.mailgun.EmailBackend"


def test_django_mail_uses_mailgun():
    assert settings_module.EMAIL_BACKEND == MAILGUN_BACKEND


def test_from_the_same_identity_as_the_apps_mail():
    assert settings.DEFAULT_FROM_EMAIL == settings.MAILGUN_FROM_ADDRESS
    assert settings.SERVER_EMAIL == settings.MAILGUN_FROM_ADDRESS


def test_configured_from_the_mailgun_settings():
    anymail = settings.ANYMAIL
    assert anymail["MAILGUN_API_KEY"] == settings.MAILGUN_SENDING_KEY
    assert anymail["MAILGUN_SENDER_DOMAIN"] == settings.MAILGUN_DOMAIN
    assert settings.MAILGUN_API_URL.startswith(anymail["MAILGUN_API_URL"])


def test_it_fails_fast():
    assert settings.ANYMAIL["REQUESTS_TIMEOUT"] == settings.EMAIL_TIMEOUT <= 10


def test_no_smtp_settings_are_required():
    """The SMTP lines can leave every .env without breaking startup."""
    source = inspect.getsource(settings_module)
    for name in ("EMAIL_HOST", "EMAIL_PORT", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD"):
        assert f"config('{name}'" not in source, f"settings.py still requires {name}"


@override_settings(ADMINS=[("Admin", "admin@example.org")], EMAIL_BACKEND=MAILGUN_BACKEND)
def test_an_error_report_is_posted_to_mailgun():
    response = MagicMock(status_code=200, headers={})
    response.json.return_value = {"id": "<m@x>", "message": "Queued. Thank you."}
    response.text = '{"id": "<m@x>"}'
    with patch("requests.Session.request", return_value=response) as request:
        mail.mail_admins("Server error", "Traceback ...")

    call = request.call_args
    method = call.kwargs.get("method") or call.args[0]
    url = call.kwargs.get("url") or call.args[1]
    assert method.upper() == "POST"
    assert url == settings.MAILGUN_API_URL
    assert request.call_args.kwargs["auth"] == ("api", settings.MAILGUN_SENDING_KEY)
    assert request.call_args.kwargs["timeout"] == settings.EMAIL_TIMEOUT
