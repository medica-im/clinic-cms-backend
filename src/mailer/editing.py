"""What an organization administrator does to its email templates.

Synchronous and free of HTTP, so api.routers.email_templates only has to
authorise, resolve the organization and translate TemplateInvalid into a 422.
"""

from django.db import transaction
from django.template import TemplateSyntaxError

from mailer.models import EmailTemplate
from mailer.templating import (
    RenderedEmail,
    TemplateProblem,
    get_template,
    invitation_context,
    render_email,
    validate_template,
)
from mailer.defaults import TemplateText

# Who a preview is addressed to unless the administrator names someone.
# Visibly made up, and at a domain reserved for examples.
SAMPLE_INVITEE_NAME = "Camille Exemple"
SAMPLE_INVITEE_EMAIL = "camille.exemple@example.org"


class TemplateInvalid(Exception):
    def __init__(self, problems: list[TemplateProblem]):
        super().__init__(", ".join(f"{p.field}:{p.code}" for p in problems))
        self.problems = problems


def effective_template(organization, kind: str):
    """(template, source): what an invitation would be sent with today, and
    whether that is the organization's own, the default or the built-in text."""
    template = get_template(organization, kind)
    if not isinstance(template, EmailTemplate):
        return template, "builtin"
    return template, "default" if template.organization_id is None else "organization"


def placeholder_values(organization, domain: str, kind: str) -> dict[str, str]:
    """What each placeholder prints for this organization, with the made-up
    invitee standing in for the invitee's own fields. The same context the
    preview renders with, so the two cannot disagree."""
    return invitation_context(organization, domain, SAMPLE_INVITEE_NAME, SAMPLE_INVITEE_EMAIL)


def _required(subject: str, body: str) -> list[TemplateProblem]:
    return [
        TemplateProblem(field, "required")
        for field, value in (("subject", subject), ("body", body))
        if not value.strip()
    ]


def save_template(organization, kind: str, *, subject: str, body: str, body_text: str, content_type: str) -> EmailTemplate:
    """Create or replace the organization's own template. Never the default."""
    problems = _required(subject, body) or validate_template(kind, subject, body, body_text)
    if problems:
        raise TemplateInvalid(problems)
    with transaction.atomic():
        row, _ = EmailTemplate.objects.update_or_create(
            organization=organization,
            kind=kind,
            defaults={
                "subject": subject,
                "body": body,
                "body_text": body_text,
                "content_type": content_type,
                "active": True,
            },
        )
    return row


def reset_template(organization, kind: str) -> bool:
    """Back to the default: delete the organization's row. True if there was one."""
    deleted, _ = EmailTemplate.objects.filter(organization=organization, kind=kind).delete()
    return bool(deleted)


def preview_template(
    organization,
    domain: str,
    kind: str,
    *,
    subject: str,
    body: str,
    body_text: str,
    content_type: str,
    invitee_name: str | None = None,
    invitee_email: str | None = None,
) -> tuple[RenderedEmail, list[TemplateProblem]]:
    """Render a draft as it would be sent, for a made-up invitee.

    Problems that still render (an unknown placeholder, a missing link) are
    returned alongside, so the preview shows them; a draft that cannot be
    rendered at all raises TemplateInvalid.
    """
    problems = validate_template(kind, subject, body, body_text)
    if any(p.code in ("syntax", "mjml_source") for p in problems):
        raise TemplateInvalid(problems)
    draft = TemplateText(subject=subject, body=body, content_type=content_type, body_text=body_text)
    context = placeholder_values(organization, domain, kind)
    if invitee_name is not None:
        context["invitee_name"] = invitee_name
    if invitee_email:
        context["invitee_email"] = invitee_email
    try:
        return render_email(draft, context), problems
    except TemplateSyntaxError as error:
        raise TemplateInvalid([TemplateProblem("body", "syntax", detail=str(error))])
