"""A template is checked when it is saved, not when an invitation goes out.

At send time a bad template never blocks an invitation: resolution falls back
past it and an unknown {{ name }} renders as itself. That keeps mail flowing,
but the organization would silently send the default without knowing why.
So saving -- in the Django admin and through the API -- refuses what cannot
be right:

* a placeholder the kind does not provide ({{ invitee_nam }}), named, so
  the typo can be found;
* an invitation without {{ signin_url }}: the email would invite without
  saying where to go;
* MJML source (<mj-...>): mail clients cannot render it; the compiled HTML
  must be pasted instead;
* a tag other than {% if %}/{% else %}, or malformed syntax.

Problems are returned as codes rather than sentences, so the frontend can
show them in the user's language; the admin turns them into English.
"""

import pytest
from django.core.exceptions import ValidationError

from mailer.defaults import INVITATION_FALLBACK, INVITATION_HTML
from mailer.models import EmailTemplate
from mailer.templating import PLACEHOLDERS, validate_template

GOOD_BODY = "<p>Bonjour {{ invitee_name }}</p><a href=\"{{ signin_url }}\">Go</a>"


def _codes(problems):
    return {(p.field, p.code) for p in problems}


def test_a_correct_template_has_no_problem():
    assert validate_template("invitation", "Hi {{ organization_name }}", GOOD_BODY, "") == []


@pytest.mark.parametrize("builtin", [INVITATION_FALLBACK, INVITATION_HTML], ids=["text", "html"])
def test_the_builtin_invitations_are_valid(builtin):
    assert validate_template("invitation", builtin.subject, builtin.body, builtin.body_text) == []


def test_every_placeholder_of_the_context_is_allowed():
    body = " ".join(f"{{{{ {name} }}}}" for name in PLACEHOLDERS["invitation"])

    assert validate_template("invitation", "S", body, "") == []


def test_an_unknown_placeholder_is_named():
    problems = validate_template("invitation", "S", GOOD_BODY + "{{ invitee_nam }}", "")

    assert [(p.field, p.code, p.names) for p in problems] == [
        ("body", "unknown_placeholder", ["invitee_nam"])
    ]


def test_an_unknown_placeholder_in_the_subject_is_reported_on_the_subject():
    problems = validate_template("invitation", "{{ nope }}", GOOD_BODY, "")

    assert _codes(problems) == {("subject", "unknown_placeholder")}


def test_an_unknown_placeholder_in_a_condition_is_reported_too():
    problems = validate_template("invitation", "S", GOOD_BODY + "{% if nope %}x{% endif %}", "")

    assert [p.names for p in problems] == [["nope"]]


def test_an_unknown_placeholder_in_the_text_alternative_is_reported_there():
    problems = validate_template("invitation", "S", GOOD_BODY, "{{ nope }}")

    assert _codes(problems) == {("body_text", "unknown_placeholder")}


def test_an_invitation_must_link_to_the_signin_page():
    problems = validate_template("invitation", "S", "<p>Bonjour</p>", "")

    assert _codes(problems) == {("body", "missing_signin_url")}


def test_mjml_source_is_refused():
    body = "<mjml><mj-body><mj-text>{{ signin_url }}</mj-text></mj-body></mjml>"

    problems = validate_template("invitation", "S", body, "")

    assert ("body", "mjml_source") in _codes(problems)


@pytest.mark.parametrize("body", ["{% debug %}{{ signin_url }}", "{% if %}{{ signin_url }}", "{{ signin_url"])
def test_a_forbidden_tag_or_malformed_syntax_is_refused(body):
    problems = validate_template("invitation", "S", body, "")

    assert _codes(problems) == {("body", "syntax")}


def test_an_empty_subject_or_body_is_left_to_the_required_fields():
    # "This field is required" already says it; no second message.
    assert validate_template("invitation", "", "", "") == []


@pytest.mark.django_db
def test_the_model_refuses_to_be_saved_with_a_problem():
    template = EmailTemplate(kind="invitation", subject="S", body="{{ nope }}", content_type="html")

    with pytest.raises(ValidationError) as caught:
        template.full_clean(validate_constraints=False)

    assert set(caught.value.message_dict) == {"body"}
    assert any("nope" in m for m in caught.value.message_dict["body"])


@pytest.mark.django_db
def test_a_valid_model_passes_its_checks():
    EmailTemplate(kind="invitation", subject="S", body=GOOD_BODY, content_type="html").full_clean(
        validate_constraints=False
    )


def test_the_template_can_be_edited_in_the_admin():
    from django.contrib import admin

    assert EmailTemplate in admin.site._registry
