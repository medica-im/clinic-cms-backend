"""Building the content of outgoing emails."""

import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser

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


@dataclass(frozen=True)
class RenderedEmail:
    """What is posted to Mailgun. html is None for a text template, so the
    request carries no html part at all."""

    subject: str
    text: str
    html: str | None = None


def render_email(template, context: dict[str, str]) -> RenderedEmail:
    """Render a template into the parts of an email.

    An HTML template always gets a text alternative -- its own body_text when
    filled, otherwise one derived from the rendered html: a message with no
    text part scores worse with spam filters and is unreadable in text-only
    clients. The subject is never escaped: it is a header, not HTML.
    """
    subject = render(template.subject, context)
    if template.content_type != "html":
        return RenderedEmail(subject=subject, text=render(template.body, context))
    html = render(template.body, context, html=True)
    if template.body_text.strip():
        text = render(template.body_text, context)
    else:
        text = html_to_text(html)
    return RenderedEmail(subject=subject, text=text, html=html)


class _TextExtractor(HTMLParser):
    """Collects what a reader sees, one block per paragraph."""

    SKIPPED = {"head", "title", "style", "script", "template"}
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}
    PARAGRAPH = {"p", "div", "table", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
                 "ul", "ol", "blockquote", "hr", "section", "article", "header", "footer"}
    LINE = {"br", "li"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0
        self.links: list[tuple[str, int]] = []

    def handle_starttag(self, tag, attrs):
        if self.skip_depth:
            if tag not in self.VOID:
                self.skip_depth += 1
            return
        attrs = dict(attrs)
        style = (attrs.get("style") or "").replace(" ", "").lower()
        if tag in self.SKIPPED or "display:none" in style:
            if tag not in self.VOID:
                self.skip_depth = 1
            return
        if tag in self.PARAGRAPH:
            self.parts.append("\n\n")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in self.LINE:
            self.parts.append("\n")
        elif tag == "a":
            self.links.append((attrs.get("href") or "", len(self.parts)))

    def handle_endtag(self, tag):
        if self.skip_depth:
            self.skip_depth -= 1
            return
        if tag in self.PARAGRAPH:
            self.parts.append("\n\n")
        elif tag == "a" and self.links:
            href, start = self.links.pop()
            label = "".join(self.parts[start:]).strip()
            # A link with no text (a linked logo) says nothing in plain text.
            if href and label and not href.startswith("#") and label != href:
                self.parts.append(f" ({href})")

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(re.sub(r"[ \t\r\n]+", " ", data))


def html_to_text(html: str) -> str:
    """A readable plain-text version of an email's html.

    Links keep their target as "text (url)", since the reader of the text
    part cannot click the words. Hidden elements (a preheader) are dropped:
    they would repeat the first line.
    """
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    lines = (re.sub(r" +", " ", line).strip(" ") for line in "".join(parser.parts).split("\n"))
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# What each kind of email can use, as {{ name }}. Must match the keys of the
# kind's context function (invitation_context).
PLACEHOLDERS = {
    "invitation": (
        "invitee_name",
        "invitee_email",
        "organization_name",
        "organization_short_name",
        "site_name",
        "site_url",
        "signin_url",
        "contact_url",
    ),
}

# A placeholder the email of that kind cannot do without.
REQUIRED_IN_BODY = {"invitation": "signin_url"}


@dataclass(frozen=True)
class TemplateProblem:
    """Why a template cannot be saved. A code, not a sentence, so the
    frontend can say it in the user's language."""

    field: str
    code: str  # syntax | unknown_placeholder | missing_signin_url | mjml_source
    names: list[str] | None = None
    detail: str = ""


def _condition_names(condition):
    """Variable names in an {% if %} condition, which is a tree of operators
    with TemplateLiteral leaves."""
    if condition is None:
        return
    value = getattr(condition, "value", None)
    if value is not None and hasattr(value, "var"):
        yield from _variable_names(value)
    for side in ("first", "second"):
        yield from _condition_names(getattr(condition, side, None))


def _variable_names(filter_expression):
    variable = filter_expression.var
    lookups = getattr(variable, "lookups", None)
    if lookups:
        yield lookups[0]


def placeholder_names(template: Template) -> set[str]:
    """Every name a compiled template reads, in {{ }} or in {% if %}."""
    names: set[str] = set()
    for node in template.nodelist.get_nodes_by_type(Node):
        if isinstance(node, VariableNode):
            names.update(_variable_names(node.filter_expression))
        elif isinstance(node, IfNode):
            for condition, _ in node.conditions_nodelists:
                names.update(_condition_names(condition))
    return names


def validate_template(kind: str, subject: str, body: str, body_text: str) -> list[TemplateProblem]:
    """What would make this template wrong to save. Empty fields are left to
    the required-field checks."""
    allowed = set(PLACEHOLDERS[kind])
    problems: list[TemplateProblem] = []
    for field, text in (("subject", subject), ("body", body), ("body_text", body_text)):
        if not text:
            continue
        if field == "body" and "<mj-" in text.lower():
            problems.append(TemplateProblem(field, "mjml_source"))
            continue
        try:
            compiled = compile_template(text)
        except TemplateSyntaxError as error:
            problems.append(TemplateProblem(field, "syntax", detail=str(error)))
            continue
        # The lexer only matches complete tags: an unclosed "{{ name" is
        # plain text and would reach the invitee as written.
        unclosed = [
            node for node in compiled.nodelist.get_nodes_by_type(TextNode)
            if "{{" in node.s or "{%" in node.s
        ]
        if unclosed:
            problems.append(TemplateProblem(field, "syntax", detail="Unclosed {{ or {%"))
            continue
        names = placeholder_names(compiled)
        unknown = sorted(names - allowed)
        if unknown:
            problems.append(TemplateProblem(field, "unknown_placeholder", names=unknown))
        required = REQUIRED_IN_BODY.get(kind)
        if field == "body" and required and required not in names:
            problems.append(TemplateProblem(field, f"missing_{required}"))
    return problems


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
        # Blank on many organizations: the full name then, never a gap.
        "organization_short_name": (
            (getattr(organization, "formatted_name_short", "") or "").strip()
            or organization.formatted_name
        ),
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
