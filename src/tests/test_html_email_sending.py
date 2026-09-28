"""An HTML template goes out as HTML, always with a plain-text alternative.

Until now every email was posted to Mailgun as "text" only, so an HTML
template would have reached the invitee as raw markup. An HTML template now
sends both parts: the html, and a text alternative -- the template's own
body_text when it is filled, otherwise one derived from the html. A message
with no text part scores worse with spam filters and is unreadable in
text-only clients.

A text template keeps sending exactly what it sent before: no "html" key at
all in the Mailgun data, so the seeded default is unchanged.
"""

from unittest.mock import MagicMock, patch

import pytest

from mailer.defaults import INVITATION_FALLBACK, INVITATION_HTML, TemplateText
from mailer.main import send_batch_emails, send_single_email
from mailer.templating import html_to_text, invitation_context, render_email

from tests.test_invitations_send_per_organization import (
    FakeOrganization,
    builtin_template,  # noqa: F401 -- a fixture, used by name below
)


def _ok_response():
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"id": "<msg@example.org>"}
    return response


def _context(name="Who"):
    return invitation_context(FakeOrganization(), "annuaire.example.org", name, "who@example.org")


# --- Posting to Mailgun -------------------------------------------------------


def test_a_single_email_with_html_posts_both_parts():
    with patch("mailer.main.requests.post", return_value=_ok_response()) as post:
        send_single_email("who@example.org", "S", "plain", html="<p>rich</p>")

    data = post.call_args.kwargs["data"]
    assert data["text"] == "plain"
    assert data["html"] == "<p>rich</p>"


def test_a_single_email_without_html_posts_no_html_key():
    with patch("mailer.main.requests.post", return_value=_ok_response()) as post:
        send_single_email("who@example.org", "S", "plain")

    assert "html" not in post.call_args.kwargs["data"]


def test_a_batch_email_with_html_posts_both_parts():
    recipients = {"who@example.org": {"name": "Who", "uid": "u1"}}
    with patch("mailer.main.requests.post", return_value=_ok_response()) as post:
        send_batch_emails(recipients, "S", "plain", html="<p>rich</p>")

    data = post.call_args.kwargs["data"]
    assert data["text"] == "plain"
    assert data["html"] == "<p>rich</p>"


def test_a_batch_email_without_html_posts_no_html_key():
    recipients = {"who@example.org": {"name": "Who", "uid": "u1"}}
    with patch("mailer.main.requests.post", return_value=_ok_response()) as post:
        send_batch_emails(recipients, "S", "plain")

    assert "html" not in post.call_args.kwargs["data"]


def test_the_single_email_task_forwards_the_html_part():
    from mailer.tasks import send_single_email_task

    with (
        patch("mailer.tasks.get_sender"),
        patch("mailer.tasks.send_single_email", return_value={}) as send,
    ):
        send_single_email_task("who@example.org", "S", "plain", html="<p>rich</p>")

    assert send.call_args.kwargs["html"] == "<p>rich</p>"


# --- Deriving the text part ---------------------------------------------------


def test_html_to_text_drops_style_and_script_contents():
    text = html_to_text(
        "<style>p { color: red; }</style><script>alert(1)</script><p>Hello</p>"
    )

    assert text == "Hello"


def test_html_to_text_keeps_the_target_of_a_link():
    text = html_to_text('<p>Go to <a href="https://x.example/signin">the site</a></p>')

    assert text == "Go to the site (https://x.example/signin)"


def test_html_to_text_does_not_repeat_a_link_whose_text_is_its_url():
    text = html_to_text('<a href="https://x.example">https://x.example</a>')

    assert text == "https://x.example"


def test_html_to_text_puts_blocks_on_their_own_lines():
    text = html_to_text("<p>One</p><p>Two</p><div>Three<br>Four</div>")

    assert text == "One\n\nTwo\n\nThree\nFour"


def test_html_to_text_drops_a_link_with_no_text():
    # A linked logo: "(https://...)" alone on a line says nothing to a reader.
    text = html_to_text('<a href="https://x.example"><img src="logo.png" alt="Logo"></a><p>Hello</p>')

    assert text == "Hello"


def test_html_to_text_marks_list_items():
    text = html_to_text("<p>Steps:</p><ol><li>One</li><li>Two</li></ol>")

    assert text == "Steps:\n\n- One\n- Two"


def test_html_to_text_unescapes_entities():
    assert html_to_text("<p>L&rsquo;&eacute;quipe &amp; co</p>") == "L’équipe & co"


def test_html_to_text_collapses_the_indentation_of_the_source():
    text = html_to_text("<table>\n  <tr>\n    <td>\n      One   two\n    </td>\n  </tr>\n</table>")

    assert text == "One two"


# --- Rendering a template into parts ------------------------------------------


def test_a_text_template_renders_no_html_part():
    email = render_email(INVITATION_FALLBACK, _context())

    assert email.html is None
    assert email.text.startswith("Bonjour Who!")


def test_an_html_template_renders_both_parts():
    email = render_email(INVITATION_HTML, _context())

    assert email.html is not None and "<html" in email.html
    assert "<" not in email.text
    assert "https://annuaire.example.org/signin" in email.text


def test_the_html_part_is_escaped_and_the_text_part_is_not():
    template = TemplateText(subject="{{ invitee_name }}", body="<p>{{ invitee_name }}</p>", content_type="html")

    email = render_email(template, _context(name="L'<b>"))

    assert email.subject == "L'<b>"
    assert "L&#x27;&lt;b&gt;" in email.html
    assert email.text == "L'<b>"


def test_a_filled_body_text_wins_over_the_derived_text():
    template = TemplateText(
        subject="S",
        body="<p>Rich {{ invitee_name }}</p>",
        content_type="html",
        body_text="Written by hand for {{ invitee_name }}",
    )

    email = render_email(template, _context())

    assert email.text == "Written by hand for Who"


# --- Both invitation paths ----------------------------------------------------


@pytest.fixture
def html_template():
    def lookup(organization, kind):
        return INVITATION_HTML

    with (
        patch("api.serializers.invitee.get_template", lookup),
        patch("mailer.templating.get_template", lookup),
    ):
        yield


@pytest.mark.asyncio
@pytest.mark.usefixtures("html_template")
async def test_a_single_invitation_queues_the_html_part():
    from unittest.mock import AsyncMock

    from api.serializers.invitee import notification_email
    from tests.test_invitations_send_per_organization import FakeInvitee, FakeSite

    with (
        patch(
            "api.serializers.invitee.Organization.objects.aget",
            new_callable=AsyncMock,
            return_value=FakeOrganization(),
        ),
        patch("api.serializers.invitee.send_single_email_task") as task,
    ):
        await notification_email(FakeInvitee(), FakeSite())

    html = task.delay.call_args.kwargs["html"]
    assert 'href="https://annuaire.example.org/signin"' in html
    assert "<" not in task.delay.call_args.args[2]


@pytest.mark.asyncio
@pytest.mark.usefixtures("html_template")
async def test_a_batch_invitation_sends_the_html_part():
    from access.tasks import _send_notification_email
    from tests.test_invitations_send_per_organization import FakeSite

    with (
        patch("django.contrib.sites.models.Site.objects.get", return_value=FakeSite()),
        patch("facility.models.Organization.objects.get", return_value=FakeOrganization()),
        patch("mailer.config.get_sender"),
        patch("mailer.main.send_single_email", return_value={}) as send,
    ):
        _send_notification_email("who@example.org", "Who", FakeSite.domain)

    html = send.call_args.kwargs["html"]
    assert 'href="https://annuaire.example.org/signin"' in html
    assert "<" not in send.call_args.args[2]


# The seeded default is text: it must keep going out as text only.


@pytest.mark.asyncio
@pytest.mark.usefixtures("builtin_template")
async def test_a_single_text_invitation_queues_no_html_part():
    from unittest.mock import AsyncMock

    from api.serializers.invitee import notification_email
    from tests.test_invitations_send_per_organization import FakeInvitee, FakeSite

    with (
        patch(
            "api.serializers.invitee.Organization.objects.aget",
            new_callable=AsyncMock,
            return_value=FakeOrganization(),
        ),
        patch("api.serializers.invitee.send_single_email_task") as task,
    ):
        await notification_email(FakeInvitee(), FakeSite())

    assert task.delay.called
    assert task.delay.call_args.kwargs.get("html") is None


@pytest.mark.usefixtures("builtin_template")
def test_a_batch_text_invitation_sends_no_html_part():
    from access.tasks import _send_notification_email
    from tests.test_invitations_send_per_organization import FakeSite

    with (
        patch("django.contrib.sites.models.Site.objects.get", return_value=FakeSite()),
        patch("facility.models.Organization.objects.get", return_value=FakeOrganization()),
        patch("mailer.config.get_sender"),
        patch("mailer.main.send_single_email", return_value={}) as send,
    ):
        _send_notification_email("who@example.org", "Who", FakeSite.domain)

    assert send.called
    assert send.call_args.kwargs.get("html") is None
