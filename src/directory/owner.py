"""The directory's owner in Neo4j, from what Django says.

    (Directory)-[:OWNED_BY]->(Entry)

Django holds the link (`Organization.directory`, `Organization.neomodel_uid`);
the graph holds a copy that the queries read. This writes the copy. It only
ever adds: two directories may share an owner (santelyon3 and
cpts-lyon-3-sante-mentale), and Django's OneToOne can describe only one of
them, so an edge Django does not mention is not an edge to remove.

See tests/api/test_directory_owner_follows_the_organization.py.
"""
import enum

from neomodel import db

# MERGE inside FOREACH: OPTIONAL MATCH keeps one row when a node is missing,
# so the query can say which one, and the edge is only written when both exist.
LINK_OWNER = """
OPTIONAL MATCH (d:Directory {name: $name})
OPTIONAL MATCH (e:Entry {uid: $uid})
OPTIONAL MATCH (d)-[existing:OWNED_BY]->(e)
WITH d, e, count(existing) > 0 AS existed
FOREACH (_ IN CASE WHEN d IS NULL OR e IS NULL THEN [] ELSE [1] END |
    MERGE (d)-[:OWNED_BY]->(e))
RETURN d IS NOT NULL, e IS NOT NULL, existed
"""


class Link(enum.Enum):
    CREATED = "created"
    EXISTED = "existed"
    NO_DIRECTORY = "no directory"
    NO_ENTRY = "no entry"


def link_directory_owner(directory_name: str, entry_uid: str) -> Link:
    """Make the entry `entry_uid` (hex) an owner of the directory `directory_name`."""
    rows, _ = db.cypher_query(LINK_OWNER, {"name": directory_name, "uid": entry_uid})
    has_directory, has_entry, existed = rows[0]
    if not has_directory:
        return Link.NO_DIRECTORY
    if not has_entry:
        return Link.NO_ENTRY
    return Link.EXISTED if existed else Link.CREATED
