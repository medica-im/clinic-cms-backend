from pydantic import BaseModel


class AdminUser(BaseModel):
    """A creator or owner, as much of them as an admin table needs.

    uid and name only — deliberately no email. The name renders the link, and
    the user detail page behind it can show the address to an admin who needs
    it. An email here would put every directory user's address into a bulk
    response, which is the kind of payload that gets logged, cached by a proxy
    or pasted into a ticket.
    """

    uid: str
    name: str | None = None


class AdminFacility(BaseModel):
    uid: str
    name: str | None = None
    slug: str | None = None


class AdminEffectorType(BaseModel):
    uid: str
    name: str | None = None
    slug: str | None = None


class AdminEntry(BaseModel):
    """One row of the administrative entries table.

    Everything here is either already public (name, slug, type, facility) or
    administrative (who created it, who owns it, when, why it was deactivated).
    The administrative half is why this type is not reachable from any
    anonymous endpoint: see api/routers/admin_entries.py.
    """

    uid: str
    slug: str | None = None
    name: str | None = None
    active: bool
    # Milliseconds since the epoch, like every other timestamp in this project.
    createdAt: int | None = None
    updatedAt: int | None = None
    # Free text written by an administrator, which may describe a person's
    # circumstances — one of the reasons this endpoint is admin-only.
    deactivation_reason: str | None = None
    deactivation_datetime: str | None = None
    # The minimum role that may see this entry in the public directory.
    access: str = "anonymous"
    effector_type: AdminEffectorType | None = None
    facility: AdminFacility | None = None
    directories: list[str] = []
    creators: list[AdminUser] = []
    owners: list[AdminUser] = []
