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


class AdminEntry(BaseModel):
    """What /api/v2/entries does not carry, keyed by uid.

    Deliberately not a whole entry. The public feed already serves the name,
    slug, type, facility, commune, department, tags, directories, access and
    active state — and serves all of them to an administrator, who is not
    filtered by access level. Repeating them here would mean a second Cypher
    walk over the same graph for a page that has already loaded the first.

    So this is the difference: the four things an audit view needs that the
    addressbook has no reason to publish. The page joins them onto the entries
    it already has, by uid.

    It stays a separate endpoint rather than four more fields on the public
    one because `deactivation_reason` is free text an administrator wrote about
    why a practitioner left, and creator/owner names identify the people who
    maintain each entry. Neither belongs in a response anonymous visitors can
    fetch, where the only thing keeping them out would be a scrub list somebody
    has to remember to update — the mechanism that already leaked restricted
    websites once.
    """

    uid: str
    # Milliseconds since the epoch, like every other timestamp in this project.
    createdAt: int | None = None
    # The most recent edit to the Postgres contact rows — phones, emails,
    # websites, the avatar. The graph node's own updatedAt is in the public
    # feed; the later of the two is when the entry actually changed.
    contactUpdatedAt: int | None = None
    # Free text, which may describe a person's circumstances.
    deactivation_reason: str | None = None
    deactivation_datetime: str | None = None
    creators: list[AdminUser] = []
    owners: list[AdminUser] = []
