"""Building the content of outgoing emails."""

import logging

from django.db.models import Q
from django.template import Context, Engine, Template, TemplateSyntaxError
from django.template.base import Node, TextNode, VariableNode
from django.template.defaulttags import IfNode

logger = logging.getLogger(__name__)


def organization_site_url(organization, domain: str) -> str:
    """Public root URL of the organization's site, with no trailing slash.

    A site served under a base path (unipa.fr/annuaire) cannot be derived from
    site.domain: nginx strips the prefix before the request reaches the
    backend. Such sites set Organization.public_base_url; every other site
    leaves it blank and gets https://{domain}.
    """
    base_url = (getattr(organization, "public_base_url", "") or "").strip()
    if base_url:
        return base_url.rstrip("/")
    return f"https://{domain}"


def organization_site_name(organization, domain: str) -> str:
    """How the site is named in prose: its public URL without the scheme.

    dev.unipa.fr/annuaire rather than dev.unipa.fr, which is the WordPress at
    the root and not the service the invitee is sent to.
    """
    return organization_site_url(organization, domain).split("://", 1)[-1]


# Standalone, not settings.TEMPLATES: no loaders, so {% include %} and
# {% extends %} find nothing, and no libraries, so {% load %} finds nothing.
# An unknown {{ name }} renders as itself, which makes a typo visible in the
# email instead of a silent blank.
ENGINE = Engine(loaders=[], libraries={}, string_if_invalid="{{ %s }}")

# The default tags cannot be removed from an Engine, so the others are refused
# here: {% debug %} would mail out the context and Python's module list.
ALLOWED_NODES = (TextNode, VariableNode, IfNode)


def compile_template(text: str) -> Template:
    """Parse text, refusing any tag but {% if %}/{% elif %}/{% else %}.

    Raises TemplateSyntaxError, both for malformed text and for a tag that is
    not allowed.
    """
    template = ENGINE.from_string(text)
    for node in template.nodelist.get_nodes_by_type(Node):
        if not isinstance(node, ALLOWED_NODES):
            tag = node.token.contents.split()[0] if node.token else type(node).__name__
            raise TemplateSyntaxError(f"Tag not allowed in an email template: {tag}")
    return template


def render(text: str, context: dict[str, str], *, html: bool = False) -> str:
    """Render text with context, escaping values only in an HTML body.

    A value is never rendered again, so an invitee named {{ x }} stays that.
    """
    return compile_template(text).render(Context(context, autoescape=html))


def compiles(template) -> bool:
    """True when every part of the template can be rendered."""
    try:
        for text in (template.subject, template.body, template.body_text):
            compile_template(text)
    except TemplateSyntaxError as error:
        logger.warning(f"Email template {template} does not compile: {error}")
        return False
    return True


def invitation_context(organization, domain: str, name: str | None, email: str) -> dict[str, str]:
    """The placeholders an invitation can use. No database access, so the
    async single-invite path and the Celery batch path share it."""
    site_url = organization_site_url(organization, domain)
    return {
        "invitee_name": name or "",
        "invitee_email": email,
        "organization_name": organization.formatted_name,
        "site_name": organization_site_name(organization, domain),
        "site_url": site_url,
        "signin_url": f"{site_url}/signin",
        "contact_url": f"{site_url}/contact",
    }


def get_template(organization, kind: str):
    """The template to send: the organization's own, else the default row,
    else the built-in text -- skipping any row that is inactive or half
    filled, so an invitation always goes out. Same shape as
    mailer.config.get_sender."""
    from mailer.defaults import INVITATION_FALLBACK
    from mailer.models import EmailTemplate

    builtin = {EmailTemplate.Kind.INVITATION: INVITATION_FALLBACK}[kind]
    if organization is None:
        return builtin

    rows = EmailTemplate.objects.filter(
        Q(organization_id=organization.id) | Q(organization__isnull=True),
        kind=kind,
    )
    by_owner = {row.organization_id: row for row in rows}
    for row in (by_owner.get(organization.id), by_owner.get(None)):
        if row is not None and row.is_usable() and compiles(row):
            return row
    logger.info(f"No usable {kind} template for {organization}; using the built-in text")
    return builtin
