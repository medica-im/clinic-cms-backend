"""Who may see and who may change an organization's emails.

Seeing is for administrators and higher, always. Changing is the role the
organization chose (Organization.email_template_editor_role) or higher.
Both compare ranks in access.role_change.HIERARCHY, so a superuser passes
wherever an administrator does, and an unknown role gets nothing.
"""

from access.role_change import rank

VIEWER_ROLE = "administrator"
EDITOR_ROLES = ("administrator", "superuser")


def may_view(role: str | None) -> bool:
    return bool(role) and rank(role) >= rank(VIEWER_ROLE)


def editor_role(organization) -> str:
    """The stored choice; anything else reads as superuser, so a bad value
    fails closed."""
    chosen = getattr(organization, "email_template_editor_role", None)
    return chosen if chosen in EDITOR_ROLES else "superuser"


def may_edit(role: str | None, organization) -> bool:
    return may_view(role) and rank(role) >= rank(editor_role(organization))
