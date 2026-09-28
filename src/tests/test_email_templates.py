"""Invitation emails come from an editable template, not from the code.

The invitation text used to be hardcoded twice -- once for the single invite
(api.serializers.invitee) and once for the batch invite (access.tasks) -- so
changing a word meant a deploy, and every organization sent the same words.

It now lives in EmailTemplate rows. An organization may own one per kind;
otherwise the default row (organization NULL) applies, and if that is
missing or unusable, the built-in constant in mailer.defaults does -- so an
invitation always goes out.

Placeholders are {{ name }}, rendered by a standalone Django template Engine
with no loaders and no tag libraries, so {% include %} and {% load %} are
refused. Only placeholders and {% if %}/{% else %} are allowed: any other tag
({% debug %} would mail out the context and Python's module list) makes the
template unusable, and resolution falls back past it. HTML bodies are
autoescaped, text bodies are not. {{ x }} also passes through MJML
untouched, which the HTML templates of step 2 rely on.

The first step is a pure extraction: the seeded default is today's text, and
both paths must send exactly what they sent before. The GOLDEN_* constants
below were captured from the hardcoded code before it was removed.
"""

import pytest
from django.db import IntegrityError, transaction
from django.template import TemplateSyntaxError

from facility.models import Organization
from mailer.defaults import INVITATION_FALLBACK
from mailer.models import EmailTemplate
from mailer.templating import compile_template, get_template, invitation_context, render

from tests.test_invitations_send_per_organization import (
    FakeOrganization,
    _batch_invitation,
    _single_invitation,
    builtin_template,  # noqa: F401 -- a fixture, used by name below
)


# --- Rendering --------------------------------------------------------------


def test_each_placeholder_is_substituted():
    assert render("Bonjour {{ invitee_name }}!", {"invitee_name": "Who"}) == "Bonjour Who!"


@pytest.mark.parametrize("spelling", ["{{x}}", "{{ x }}", "{{   x  }}"])
def test_whitespace_inside_the_braces_does_not_matter(spelling):
    assert render(f"<{spelling}>", {"x": "1"}) == "<1>"


def test_an_unknown_placeholder_is_left_as_written():
    # Rendering must never raise at send time: the invitation still goes out,
    # and the literal makes the typo visible to whoever receives it.
    assert render("{{ nope }} {{ x }}", {"x": "1"}) == "{{ nope }} 1"


def test_css_braces_survive():
    body = "<style>p { color: red; } a{margin:0}</style><p>{{ x }}</p>"
    assert render(body, {"x": "1"}) == "<style>p { color: red; } a{margin:0}</style><p>1</p>"


def test_a_value_is_not_rendered_again():
    # An invitee named "{{ signin_url }}" must not turn into a link.
    assert render("{{ a }}", {"a": "{{ b }}", "b": "x"}) == "{{ b }}"


def test_values_are_escaped_in_an_html_body():
    # An invitee named "<a href=...>" must not put a link in the email.
    assert render("<p>{{ x }}</p>", {"x": '<a href="x">'}, html=True) == (
        "<p>&lt;a href=&quot;x&quot;&gt;</p>"
    )


def test_values_are_not_escaped_in_a_text_body():
    assert render("{{ x }}", {"x": "L'<b>"}) == "L'<b>"


@pytest.mark.parametrize("name, expected", [("Who", "Bonjour Who!"), ("", "Bonjour!")])
def test_a_conditional_greets_an_invitee_without_a_name(name, expected):
    text = "{% if invitee_name %}Bonjour {{ invitee_name }}{% else %}Bonjour{% endif %}!"
    assert render(text, {"invitee_name": name}) == expected


@pytest.mark.parametrize(
    "body",
    [
        "{% debug %}",  # would mail out the context and sys.modules
        '{% now "Y" %}',
        '{% include "admin/base.html" %}',
        "{% load static %}",
        "{% if x %}unclosed",
        "{{ x|nosuchfilter }}",
    ],
    ids=["debug", "now", "include", "load", "unclosed", "unknown-filter"],
)
def test_a_body_with_anything_but_placeholders_and_if_is_rejected(body):
    with pytest.raises(TemplateSyntaxError):
        compile_template(body)


@pytest.mark.django_db
def test_an_organization_template_that_does_not_compile_falls_back_to_the_default():
    _clear_default()
    _row(None, subject="default")
    org = _org()
    _row(org, subject="own", body="{% debug %}")

    assert get_template(org, "invitation").subject == "default"


@pytest.mark.django_db
def test_a_subject_that_does_not_compile_falls_back_too():
    _clear_default()
    _row(None, subject="default")
    org = _org()
    _row(org, subject="{% if %}")

    assert get_template(org, "invitation").subject == "default"


def test_the_invitation_context_names_every_placeholder():
    org = FakeOrganization()
    org.public_base_url = "https://example.org/annuaire"

    context = invitation_context(org, "example.org", name="Who", email="who@example.org")

    assert context == {
        "invitee_name": "Who",
        "invitee_email": "who@example.org",
        "organization_name": "Cabinet Example",
        "organization_short_name": "Cab. Ex.",
        "site_name": "example.org/annuaire",
        "site_url": "https://example.org/annuaire",
        "signin_url": "https://example.org/annuaire/signin",
        "contact_url": "https://example.org/annuaire/contact",
    }


def test_an_organization_without_a_short_name_is_named_in_full():
    # A blank short name would leave a gap in the sentence it was put in.
    org = FakeOrganization()
    org.formatted_name_short = "  "

    context = invitation_context(org, "example.org", name="Who", email="who@example.org")

    assert context["organization_short_name"] == "Cabinet Example"


def test_a_missing_invitee_name_renders_empty():
    context = invitation_context(FakeOrganization(), "a.example.org", name=None, email="w@x.org")
    assert context["invitee_name"] == ""


# --- Resolution: organization row > default row > built-in constant ---------


def _org(name="Cabinet"):
    return Organization.objects.create(name=name)


def _row(organization=None, **fields):
    values = {
        "kind": EmailTemplate.Kind.INVITATION,
        "subject": "subject",
        "body": "body {{ signin_url }}",
        "content_type": EmailTemplate.ContentType.TEXT,
    }
    values.update(fields)
    return EmailTemplate.objects.create(organization=organization, **values)


def _clear_default():
    EmailTemplate.objects.filter(organization__isnull=True).delete()


@pytest.mark.django_db
def test_the_migration_seeds_todays_text_as_the_default():
    default = EmailTemplate.objects.get(organization__isnull=True, kind="invitation")

    assert default.content_type == EmailTemplate.ContentType.TEXT
    assert default.subject == INVITATION_FALLBACK.subject
    assert default.body == INVITATION_FALLBACK.body
    assert default.active


@pytest.mark.django_db
def test_an_organization_template_wins_over_the_default():
    org = _org()
    own = _row(org, subject="own")

    assert get_template(org, "invitation").subject == own.subject


@pytest.mark.django_db
def test_an_organization_without_a_template_gets_the_default():
    _clear_default()
    _row(None, subject="default")

    assert get_template(_org(), "invitation").subject == "default"


@pytest.mark.django_db
def test_an_inactive_organization_template_falls_back_to_the_default():
    _clear_default()
    _row(None, subject="default")
    org = _org()
    _row(org, subject="own", active=False)

    assert get_template(org, "invitation").subject == "default"


@pytest.mark.django_db
def test_a_half_filled_organization_template_falls_back_to_the_default():
    # A blank body must not go out as an empty email.
    _clear_default()
    _row(None, subject="default")
    org = _org()
    _row(org, subject="own", body="")

    assert get_template(org, "invitation").subject == "default"


@pytest.mark.django_db
def test_with_no_usable_row_the_builtin_text_applies():
    _clear_default()

    template = get_template(_org(), "invitation")

    assert template.subject == INVITATION_FALLBACK.subject
    assert template.body == INVITATION_FALLBACK.body


@pytest.mark.django_db
def test_an_inactive_default_falls_back_to_the_builtin_text():
    _clear_default()
    _row(None, subject="default", active=False)

    assert get_template(_org(), "invitation").subject == INVITATION_FALLBACK.subject


@pytest.mark.django_db
def test_one_organizations_template_never_reaches_another():
    _clear_default()
    _row(_org("A"), subject="A's own")

    assert get_template(_org("B"), "invitation").subject == INVITATION_FALLBACK.subject


def test_an_unknown_organization_gets_the_builtin_text_without_a_query():
    # organization None happens when a Site has no Organization.
    assert get_template(None, "invitation").subject == INVITATION_FALLBACK.subject


# --- Constraints: one template per organization and kind, one default --------


@pytest.mark.django_db
def test_an_organization_has_one_template_per_kind():
    org = _org()
    _row(org)
    with pytest.raises(IntegrityError), transaction.atomic():
        _row(org)


@pytest.mark.django_db
def test_there_is_one_default_per_kind():
    # Postgres NULLs are not equal, so the (organization, kind) constraint
    # alone would allow any number of defaults.
    with pytest.raises(IntegrityError), transaction.atomic():
        _row(None)  # the migration already seeded one


# --- The extraction changes nothing that is sent ------------------------------

GOLDEN_SUBJECT = "Cabinet Example vous invite à utiliser le service annuaire.example.org"
GOLDEN_MESSAGE = (
    "Bonjour Who!\n\n"
    "Cabinet Example vous invite à créer un compte sur le service en ligne "
    "annuaire.example.org. Vous pouvez vous rendre à l'adresse suivante:\n\n"
    "https://annuaire.example.org/signin\n\n"
    "et cliquer sur \"Se connecter avec Google\". Vous devez utiliser l'adresse "
    "mail suivante: who@example.org Si vous n'avez pas de compte Google lié à "
    "cette adresse, vous pourrez en créer un gratuitement en moins d'une minute. "
    "Il n'est pas nécessaire de créer une adresse Gmail! Votre mail habituel "
    "who@example.org est suffisant.\n\n"
    "Si vous devez créer un compte Google, lors de l'étape \"Méthode de connexion "
    "au compte\", ne remplissez pas le champ \"Nom d'utilisateur  ...@gmail.com\". "
    "Cliquez sur \"Utiliser l'adresse email existante\".\n\n"
    "Après authentification par le service \"Se connecter avec Google\", votre "
    "compte sur annuaire.example.org sera créé automatiquement. Vous pourrez "
    "utiliser nos services et créer votre entrée dans l'annuaire de "
    "l'organisation.\n\n"
    "En cas de problème, merci de nous contacter via "
    "https://annuaire.example.org/contact\n\n"
    "Si vous souhaitez utiliser une autre adresse électronique pour vous "
    "connecter à notre service, contactez-nous et nous vous enverrons une "
    "nouvelle invitation."
)


# Together with test_the_migration_seeds_todays_text_as_the_default, this
# proves the seeded default sends today's bytes. The two halves are split
# because the paths' helpers stub get_template with the built-in text: an
# async test with real database access would have to be transactional, and
# that truncates the tables -- the seeded default with them -- for every test
# that runs after it.
@pytest.mark.asyncio
@pytest.mark.usefixtures("builtin_template")
@pytest.mark.parametrize("build", [_single_invitation, _batch_invitation], ids=["single", "batch"])
async def test_the_builtin_text_sends_exactly_what_was_sent_before(build):
    subject, message = await build(FakeOrganization())

    assert subject == GOLDEN_SUBJECT
    assert message == GOLDEN_MESSAGE


# --- The HTML invitation ------------------------------------------------------
#
# The same message as the text default, as email HTML: tables and inline
# styles, no external resources. Not the seeded default yet -- nothing sends
# an html part before step 2.


def _render_html(name="Who", email="who@example.org", base_url=""):
    from mailer.defaults import INVITATION_HTML

    org = FakeOrganization()
    org.public_base_url = base_url
    context = invitation_context(org, "annuaire.example.org", name=name, email=email)
    return render(INVITATION_HTML.body, context, html=True)


def test_the_html_invitation_is_an_html_template_with_the_text_subject():
    from mailer.defaults import INVITATION_HTML

    assert INVITATION_HTML.content_type == "html"
    assert INVITATION_HTML.subject == INVITATION_FALLBACK.subject


def test_the_html_invitation_compiles_under_the_restricted_engine():
    from mailer.defaults import INVITATION_HTML

    compile_template(INVITATION_HTML.body)


def test_the_html_invitation_leaves_no_placeholder_unfilled():
    html = _render_html()

    assert "{{" not in html and "{%" not in html


def test_the_html_invitation_says_everything_the_text_one_does():
    html = _render_html()

    for fragment in (
        "Bonjour Who,",
        "Cabinet Example",
        "annuaire.example.org",
        'href="https://annuaire.example.org/signin"',
        'href="https://annuaire.example.org/contact"',
        "who@example.org",
        "Se connecter avec Google",
        "Utiliser l’adresse email existante",
        "nouvelle invitation",
    ):
        assert fragment in html, fragment


def test_the_html_invitation_links_under_a_base_path():
    html = _render_html(base_url="https://example.org/annuaire")

    assert 'href="https://example.org/annuaire/signin"' in html
    assert "example.org/annuaire" in html


def test_the_html_invitation_greets_an_invitee_without_a_name():
    html = _render_html(name="")

    assert "Bonjour," in html
    assert "Bonjour ," not in html


def test_the_html_invitation_escapes_what_the_invitee_typed():
    html = _render_html(name='<a href="https://evil.example">x</a>')

    assert "evil.example\"" not in html
    assert "&lt;a href=&quot;https://evil.example&quot;&gt;" in html


def test_the_html_invitation_loads_nothing_from_elsewhere():
    # Mail clients block remote resources by default, and a tracking pixel is
    # not ours to add.
    html = _render_html()

    assert "<img" not in html
    assert "<link" not in html
    assert "<script" not in html
    assert "url(" not in html
