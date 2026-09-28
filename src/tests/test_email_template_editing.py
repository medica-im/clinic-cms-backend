"""What an organization administrator does to its email templates.

The FastAPI router (api.routers.email_templates) is a thin shell over these
functions; the rules live here, synchronous, so they can be tested against the
database without the thread hop of an async test (which would need a
transactional database, and that truncates the seeded default template for
every test after it).

* Reading shows the template actually in effect and where it comes from --
  the organization's own, the default, or the built-in text -- so the
  administrator knows whether an edit would change anything for them alone.
* Saving validates first (mailer.templating.validate_template) and refuses
  with the problems; it upserts the organization's row and never touches the
  default, which is shared by every organization.
* Going back to the default deletes the organization's row.
* A preview renders a draft -- not necessarily saved -- for a made-up
  invitee, with the organization's real links, so what is seen is what would
  be sent.
"""

import pytest

from facility.models import Organization
from mailer.editing import (
    SAMPLE_INVITEE_EMAIL,
    SAMPLE_INVITEE_NAME,
    TemplateInvalid,
    effective_template,
    placeholder_values,
    preview_template,
    reset_template,
    save_template,
)
from mailer.models import EmailTemplate
from mailer.templating import PLACEHOLDERS

pytestmark = pytest.mark.django_db

GOOD = {
    "subject": "{{ organization_name }} vous invite",
    "body": '<p>Bonjour {{ invitee_name }}</p><a href="{{ signin_url }}">Go</a>',
    "body_text": "",
    "content_type": "html",
}


def _org(name="Cabinet", **fields):
    return Organization.objects.create(name=name, **fields)


# --- Reading ------------------------------------------------------------------


def test_an_organization_without_its_own_sees_the_default():
    template, source = effective_template(_org(), "invitation")

    assert source == "default"
    assert template == EmailTemplate.objects.get(organization__isnull=True, kind="invitation")


def test_an_organization_with_its_own_sees_it():
    org = _org()
    save_template(org, "invitation", **GOOD)

    template, source = effective_template(org, "invitation")

    assert source == "organization"
    assert template.subject == GOOD["subject"]


def test_with_no_default_the_builtin_text_is_shown():
    EmailTemplate.objects.filter(organization__isnull=True).delete()

    _, source = effective_template(_org(), "invitation")

    assert source == "builtin"


def test_each_placeholder_is_shown_with_its_value_for_this_site():
    # So the administrator sees what "Nom court de votre organisation" will
    # actually print, before writing it into a template.
    org = _org(formatted_name="CPTS Lyon 3ème", formatted_name_short="CPTS Lyon 3")

    values = placeholder_values(org, "santelyon3.fr", "invitation")

    assert values["organization_name"] == "CPTS Lyon 3ème"
    assert values["organization_short_name"] == "CPTS Lyon 3"
    assert values["signin_url"] == "https://santelyon3.fr/signin"
    assert values["invitee_name"] == SAMPLE_INVITEE_NAME
    assert set(values) == set(PLACEHOLDERS["invitation"])


# --- Saving -------------------------------------------------------------------


def test_saving_creates_the_organization_row():
    org = _org()

    row = save_template(org, "invitation", **GOOD)

    assert row.organization == org and row.active
    assert row.content_type == "html"


def test_saving_again_updates_the_same_row():
    org = _org()
    first = save_template(org, "invitation", **GOOD)

    second = save_template(org, "invitation", **{**GOOD, "subject": "Autre"})

    assert second.pk == first.pk
    assert EmailTemplate.objects.filter(organization=org).count() == 1
    assert second.subject == "Autre"


def test_saving_reactivates_a_row_deactivated_in_the_admin():
    org = _org()
    row = save_template(org, "invitation", **GOOD)
    EmailTemplate.objects.filter(pk=row.pk).update(active=False)

    assert save_template(org, "invitation", **GOOD).active


def test_saving_never_touches_the_default():
    default_before = EmailTemplate.objects.get(organization__isnull=True, kind="invitation")

    save_template(_org(), "invitation", **GOOD)

    default_after = EmailTemplate.objects.get(organization__isnull=True, kind="invitation")
    assert (default_after.subject, default_after.body) == (default_before.subject, default_before.body)


def test_an_invalid_template_is_refused_with_its_problems_and_not_saved():
    org = _org()

    with pytest.raises(TemplateInvalid) as caught:
        save_template(org, "invitation", **{**GOOD, "body": "<p>{{ invitee_nam }}</p>"})

    codes = {(p.field, p.code) for p in caught.value.problems}
    assert codes == {("body", "unknown_placeholder"), ("body", "missing_signin_url")}
    assert not EmailTemplate.objects.filter(organization=org).exists()


def test_an_empty_subject_or_body_is_refused():
    with pytest.raises(TemplateInvalid) as caught:
        save_template(_org(), "invitation", **{**GOOD, "subject": " ", "body": ""})

    assert {(p.field, p.code) for p in caught.value.problems} == {
        ("subject", "required"),
        ("body", "required"),
    }


# --- Going back to the default ------------------------------------------------


def test_reset_deletes_the_organization_row():
    org = _org()
    save_template(org, "invitation", **GOOD)

    assert reset_template(org, "invitation") is True

    assert effective_template(org, "invitation")[1] == "default"


def test_reset_without_a_row_is_harmless():
    assert reset_template(_org(), "invitation") is False


def test_reset_leaves_other_organizations_alone():
    mine, theirs = _org("Mine"), _org("Theirs")
    save_template(mine, "invitation", **GOOD)
    save_template(theirs, "invitation", **GOOD)

    reset_template(mine, "invitation")

    assert EmailTemplate.objects.filter(organization=theirs).exists()


# --- Preview ------------------------------------------------------------------


def test_a_preview_uses_a_made_up_invitee_and_the_real_links():
    org = _org(public_base_url="https://example.org/annuaire")

    email, problems = preview_template(org, "example.org", "invitation", **GOOD)

    assert problems == []
    assert SAMPLE_INVITEE_NAME in email.html
    assert 'href="https://example.org/annuaire/signin"' in email.html
    assert email.text  # an html template always has a text part


def test_a_preview_can_name_its_own_invitee():
    email, _ = preview_template(
        _org(), "example.org", "invitation", **GOOD,
        invitee_name="Dr Test", invitee_email="test@example.org",
    )

    assert "Dr Test" in email.html


def test_a_preview_of_a_text_template_has_no_html():
    email, _ = preview_template(
        _org(), "example.org", "invitation",
        **{**GOOD, "content_type": "text", "body": "Bonjour {{ invitee_name }} {{ signin_url }}"},
    )

    assert email.html is None
    assert email.text.startswith(f"Bonjour {SAMPLE_INVITEE_NAME}")


def test_a_preview_renders_despite_an_unknown_placeholder_and_reports_it():
    # Seeing the literal {{ typo }} in the preview is how it gets found.
    email, problems = preview_template(
        _org(), "example.org", "invitation", **{**GOOD, "body": GOOD["body"] + "{{ typo }}"}
    )

    assert "{{ typo }}" in email.html
    assert [p.names for p in problems] == [["typo"]]


def test_a_preview_that_cannot_compile_is_refused():
    with pytest.raises(TemplateInvalid):
        preview_template(_org(), "example.org", "invitation", **{**GOOD, "body": "{% debug %}"})


def test_the_sample_invitee_is_obviously_made_up():
    assert SAMPLE_INVITEE_EMAIL.endswith("@example.org")
