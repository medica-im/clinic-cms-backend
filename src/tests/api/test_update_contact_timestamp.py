"""`update_contact_timestamp` stamps whichever node a contact belongs to.

Sync `db` code, reached from Django signals. A contact's uid names a Facility
(hex), an old-structure LOCATION relationship (dashed) or an Entry (dashed), and
the function tries them in that order, stopping at the first that matches. A
uid that matches nothing, or is not a uid, is not an error.
"""
import uuid

import pytest
from asgiref.sync import sync_to_async
from neomodel import adb

from directory.timestamp import update_contact_timestamp

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def stamp(node_query, params):
    rows, _ = await adb.cypher_query(node_query, params)
    return rows[0][0]


async def test_a_facility_is_stamped(neo4j_graph):
    uid = uuid.uuid4()
    await adb.cypher_query("CREATE (:Facility {uid: $uid})", {"uid": uid.hex})

    await sync_to_async(update_contact_timestamp)(uid)

    assert await stamp("MATCH (f:Facility {uid: $uid}) RETURN f.contactUpdatedAt", {"uid": uid.hex}) is not None


async def test_a_uid_given_as_a_string_is_parsed(neo4j_graph):
    uid = uuid.uuid4()
    await adb.cypher_query("CREATE (:Facility {uid: $uid})", {"uid": uid.hex})

    await sync_to_async(update_contact_timestamp)(str(uid))

    assert await stamp("MATCH (f:Facility {uid: $uid}) RETURN f.contactUpdatedAt", {"uid": uid.hex}) is not None


async def test_a_location_of_the_old_structure_is_stamped(neo4j_graph):
    uid = uuid.uuid4()
    await adb.cypher_query(
        "CREATE (:Facility {uid: $facility})-[:LOCATION {uid: $uid}]->(:Effector {uid: $effector})",
        {"facility": uuid.uuid4().hex, "effector": uuid.uuid4().hex, "uid": str(uid)},
    )

    await sync_to_async(update_contact_timestamp)(uid)

    assert await stamp(
        "MATCH ()-[r:LOCATION {uid: $uid}]->() RETURN r.contactUpdatedAt", {"uid": str(uid)}
    ) is not None


async def test_an_entry_is_stamped(neo4j_graph):
    uid = uuid.uuid4()
    await adb.cypher_query("CREATE (:Entry {uid: $uid})", {"uid": str(uid)})

    await sync_to_async(update_contact_timestamp)(uid)

    assert await stamp("MATCH (e:Entry {uid: $uid}) RETURN e.contactUpdatedAt", {"uid": str(uid)}) is not None


async def test_the_first_match_wins(neo4j_graph):
    """A facility found by its hex uid ends the search: an entry sharing the dashed uid is left alone."""
    uid = uuid.uuid4()
    await adb.cypher_query(
        "CREATE (:Facility {uid: $hex}), (:Entry {uid: $dashed})", {"hex": uid.hex, "dashed": str(uid)}
    )

    await sync_to_async(update_contact_timestamp)(uid)

    assert await stamp("MATCH (e:Entry {uid: $uid}) RETURN e.contactUpdatedAt", {"uid": str(uid)}) is None


async def test_a_uid_that_matches_nothing_changes_nothing(neo4j_graph):
    await adb.cypher_query("CREATE (:Facility {uid: 'other'})")

    await sync_to_async(update_contact_timestamp)(uuid.uuid4())

    assert await stamp("MATCH (f:Facility) RETURN f.contactUpdatedAt", {}) is None


async def test_a_string_that_is_not_a_uid_is_ignored(neo4j_graph):
    await adb.cypher_query("CREATE (:Facility {uid: 'other'})")

    assert await sync_to_async(update_contact_timestamp)("not-a-uuid") is None
    assert await stamp("MATCH (f:Facility) RETURN f.contactUpdatedAt", {}) is None
