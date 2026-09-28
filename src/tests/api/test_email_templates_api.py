"""The HTTP contract of /api/v2/email-templates.

The rules themselves -- which template is in effect, what may be saved, how a
preview is rendered -- are tested in tests/test_email_template_editing.py.
This file pins what the frontend relies on: the paths, the gate, the shape of
the answers, and a 422 that lists problems as codes it can translate.

Access (api.email_access, rules in mailer.access): administrators and higher
may read and preview; changing is for the role the organization chose
(Organization.email_template_editor_role, superusers only by default).
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mailer.defaults import INVITATION_FALLBACK
from mailer.editing import TemplateInvalid
from mailer.templating import RenderedEmail, TemplateProblem

pytestmark = pytest.mark.asyncio

URL = "/api/v2/email-templates/invitation"
DRAFT = {
    "subject": "S {{ organization_name }}",
    "body": '<a href="{{ signin_url }}">x</a>',
    "body_text": "",
    "content_type": "html",
}


class FakeSite:
    domain = "annuaire.example.org"


@pytest.fixture
def organization():
    return MagicMock(id=7, name="Cabinet", email_template_editor_role="superuser")


@pytest.fixture
def role():
    return "superuser"


@pytest.fixture
def gate(organization, role):
    """Signed in with `role` on a site with an organization. Override the
    role or organization fixture to change who is asking."""
    from main import app
    from api.auth import JWT

    app.dependency_overrides[JWT] = lambda: {"sub": "someone"}
    lookup_role = AsyncMock(return_value=role)
    with (
        patch("api.email_access.get_neo4j_role", lookup_role),
        patch(
            "api.email_access.get_site_from_request",
            AsyncMock(return_value=FakeSite()),
        ),
        patch(
            "api.email_access.Organization.objects.aget",
            AsyncMock(return_value=organization),
        ),
    ):
        try:
            yield {"role": lookup_role}
        finally:
            app.dependency_overrides.pop(JWT, None)


@contextmanager
def service(name, **kwargs):
    with patch(f"api.routers.email_templates.{name}", MagicMock(**kwargs)) as mock:
        yield mock


# --- The gate -----------------------------------------------------------------

ROUTES = [
    ("GET", URL, None),
    ("PUT", URL, DRAFT),
    ("DELETE", URL, None),
    ("POST", URL + "/preview", DRAFT),
]
WRITES = [("PUT", URL, DRAFT), ("DELETE", URL, None)]


def all_services():
    from contextlib import ExitStack

    stack = ExitStack()
    mocks = {
        "effective_template": stack.enter_context(service("effective_template", return_value=(INVITATION_FALLBACK, "builtin"))),
        "placeholder_values": stack.enter_context(service("placeholder_values", return_value={})),
        "save_template": stack.enter_context(service("save_template", return_value=MagicMock(**DRAFT, updated=None))),
        "reset_template": stack.enter_context(service("reset_template", return_value=True)),
        "preview_template": stack.enter_context(service("preview_template", return_value=(RenderedEmail("s", "t", "<p>h</p>"), []))),
    }
    return stack, mocks


@pytest.mark.parametrize("role", ["staff", "registered", None])
@pytest.mark.parametrize("method, path, body", ROUTES)
async def test_below_administrator_every_route_is_refused(versioned_client, gate, method, path, body):
    stack, mocks = all_services()
    with stack:
        response = await versioned_client.request(method, path, json=body)

    assert response.status_code == 403
    assert not any(mock.called for mock in mocks.values())


@pytest.mark.parametrize("role", ["administrator"])
async def test_an_administrator_may_read_and_preview_what_superusers_edit(versioned_client, gate):
    stack, _ = all_services()
    with stack:
        read = await versioned_client.get(URL)
        preview = await versioned_client.post(URL + "/preview", json=DRAFT)

    assert read.status_code == 200 and read.json()["can_edit"] is False
    assert read.json()["editor_role"] == "superuser"
    assert preview.status_code == 200


@pytest.mark.parametrize("role", ["administrator"])
@pytest.mark.parametrize("method, path, body", WRITES)
async def test_an_administrator_changes_nothing_when_superusers_edit(versioned_client, gate, method, path, body):
    stack, mocks = all_services()
    with stack:
        response = await versioned_client.request(method, path, json=body)

    assert response.status_code == 403
    assert response.json()["detail"] == {"code": "not_editor"}
    assert not mocks["save_template"].called and not mocks["reset_template"].called


@pytest.mark.parametrize("role", ["administrator"])
@pytest.mark.parametrize("method, path, body", WRITES)
async def test_an_administrator_may_change_when_the_organization_lets_them(
    versioned_client, gate, organization, method, path, body
):
    organization.email_template_editor_role = "administrator"
    stack, _ = all_services()
    with stack:
        response = await versioned_client.request(method, path, json=body)

    assert response.status_code in (200, 204)


async def test_a_superuser_is_told_they_may_edit(versioned_client, gate):
    stack, _ = all_services()
    with stack:
        response = await versioned_client.get(URL)

    assert response.json()["can_edit"] is True


async def test_an_unknown_kind_is_not_found(versioned_client, gate):
    response = await versioned_client.get("/api/v2/email-templates/newsletter")

    assert response.status_code == 404


async def test_a_site_without_an_organization_is_not_found(versioned_client, gate):
    from facility.models import Organization

    with patch(
        "api.email_access.Organization.objects.aget",
        AsyncMock(side_effect=Organization.DoesNotExist),
    ):
        response = await versioned_client.get(URL)

    assert response.status_code == 404


# --- Reading ------------------------------------------------------------------


async def test_reading_answers_the_template_its_source_and_the_placeholders(versioned_client, gate):
    with (
        service("effective_template", return_value=(INVITATION_FALLBACK, "builtin")),
        service("placeholder_values", return_value={}),
    ):
        response = await versioned_client.get(URL)

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "builtin"
    assert data["subject"] == INVITATION_FALLBACK.subject
    assert data["body"] == INVITATION_FALLBACK.body
    assert data["content_type"] == "text"
    assert "signin_url" in data["placeholders"]
    assert data["required_placeholders"] == ["signin_url"]


async def test_reading_answers_what_each_placeholder_prints_on_this_site(versioned_client, gate, organization):
    with (
        service("effective_template", return_value=(INVITATION_FALLBACK, "builtin")),
        service("placeholder_values", return_value={"organization_short_name": "CPTS Lyon 3"}) as values,
    ):
        response = await versioned_client.get(URL)

    assert response.json()["placeholder_values"] == {"organization_short_name": "CPTS Lyon 3"}
    assert values.call_args.args == (organization, FakeSite.domain, "invitation")


# --- Saving -------------------------------------------------------------------


async def test_saving_passes_the_draft_for_the_sites_organization(versioned_client, gate, organization):
    saved = MagicMock(**DRAFT, updated=None)
    with (
        service("save_template", return_value=saved) as save,
        service("placeholder_values", return_value={}),
    ):
        response = await versioned_client.put(URL, json=DRAFT)

    assert response.status_code == 200
    assert response.json()["source"] == "organization"
    assert save.call_args.args == (organization, "invitation")
    assert save.call_args.kwargs == DRAFT


async def test_an_invalid_draft_is_a_422_listing_its_problems(versioned_client, gate):
    problems = [TemplateProblem("body", "unknown_placeholder", names=["invitee_nam"])]
    with service("save_template", side_effect=TemplateInvalid(problems)):
        response = await versioned_client.put(URL, json=DRAFT)

    assert response.status_code == 422
    assert response.json()["detail"]["problems"] == [
        {"field": "body", "code": "unknown_placeholder", "names": ["invitee_nam"], "detail": ""}
    ]


async def test_a_content_type_other_than_html_or_text_is_refused(versioned_client, gate):
    with service("save_template") as save:
        response = await versioned_client.put(URL, json={**DRAFT, "content_type": "mjml"})

    assert response.status_code == 422
    save.assert_not_called()


# --- Going back to the default ------------------------------------------------


async def test_deleting_goes_back_to_the_default(versioned_client, gate, organization):
    with service("reset_template", return_value=True) as reset:
        response = await versioned_client.delete(URL)

    assert response.status_code == 204
    assert reset.call_args.args == (organization, "invitation")


# --- Preview ------------------------------------------------------------------


async def test_a_preview_answers_the_parts_and_any_problems(versioned_client, gate, organization):
    problems = [TemplateProblem("body", "unknown_placeholder", names=["typo"])]
    rendered = RenderedEmail("Sujet", "texte", "<p>html</p>")
    with service("preview_template", return_value=(rendered, problems)) as preview:
        response = await versioned_client.post(
            URL + "/preview", json={**DRAFT, "invitee_name": "Dr Test"}
        )

    assert response.status_code == 200
    assert response.json() == {
        "subject": "Sujet",
        "text": "texte",
        "html": "<p>html</p>",
        "problems": [{"field": "body", "code": "unknown_placeholder", "names": ["typo"], "detail": ""}],
    }
    assert preview.call_args.args == (organization, FakeSite.domain, "invitation")
    assert preview.call_args.kwargs["invitee_name"] == "Dr Test"
    assert preview.call_args.kwargs["invitee_email"] is None


async def test_a_preview_that_cannot_render_is_a_422(versioned_client, gate):
    problems = [TemplateProblem("body", "syntax", detail="bad")]
    with service("preview_template", side_effect=TemplateInvalid(problems)):
        response = await versioned_client.post(URL + "/preview", json=DRAFT)

    assert response.status_code == 422
    assert response.json()["detail"]["problems"][0]["code"] == "syntax"
