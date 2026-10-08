"""A scanner probing the server is refused, and nobody is mailed about it.

Every public IP is scanned around the clock, mostly by IP rather than by name.
ALLOWED_HOSTS turns those requests away with a 400, but Django logs each refusal
as an ERROR on django.security.DisallowedHost, which by default propagates to
the mail_admins handler: one email per probe. Error reports are only worth
reading while each one means something is broken on our side, so a refused host
is dropped -- and a genuine server error must still reach ADMINS.
"""
import logging

from django.core import mail
from django.test import Client, override_settings

ADMINS = [("Admin", "admin@example.org")]


@override_settings(ADMINS=ADMINS)
def test_a_request_for_an_unknown_host_is_refused_without_mailing_admins():
    response = Client().get(
        "/admin/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php",
        HTTP_HOST="152.53.2.179",
    )

    assert response.status_code == 400
    assert mail.outbox == []


@override_settings(ADMINS=ADMINS)
def test_a_server_error_still_mails_admins():
    logging.getLogger("django.request").error(
        "Internal Server Error: /", extra={"status_code": 500}
    )

    assert len(mail.outbox) == 1
