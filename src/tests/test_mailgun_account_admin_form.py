"""The stored API key is never rendered back into the admin page.

An administrator editing the From name must not have to re-type the
credential, and the credential must not be sitting in the HTML of every
change page. The form therefore renders an empty password field and treats a
blank submission as "keep what is stored".
"""

import pytest

from mailer.admin import MailgunAccountForm
from mailer.models import MailgunAccount


STORED_KEY = "stored-secret-key"


def _account(**overrides):
    fields = {
        "id": 1,
        "domain": "mail.example.org",
        "region": "eu",
        "sending_key_id": "key-id",
        "api_key": STORED_KEY,
        "from_email": "contact@example.org",
        "from_name": "Cabinet Example",
        "active": True,
    }
    fields.update(overrides)
    return MailgunAccount(**fields)


def test_the_stored_key_is_not_rendered_into_the_page():
    form = MailgunAccountForm(instance=_account())

    assert STORED_KEY not in form.as_p()


def test_a_blank_submission_keeps_the_stored_key():
    form = MailgunAccountForm(instance=_account())
    form.cleaned_data = {"api_key": ""}

    assert form.clean_api_key() == STORED_KEY


def test_a_submitted_key_replaces_the_stored_one():
    form = MailgunAccountForm(instance=_account())
    form.cleaned_data = {"api_key": "new-key"}

    assert form.clean_api_key() == "new-key"


def test_a_new_account_must_be_given_a_key():
    from django.forms import ValidationError

    form = MailgunAccountForm()
    form.cleaned_data = {"api_key": ""}

    with pytest.raises(ValidationError):
        form.clean_api_key()
