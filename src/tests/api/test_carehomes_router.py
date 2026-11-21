"""GET /carehomes/{uid}: the bed counts of a care home.

One CareHome node read through neomodel (`resolve_objects=True`), so the row is
`results[0][0]`, an inflated node, and an unknown uid is an empty result that
has to become a 404 rather than an IndexError.
"""
import uuid

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def make_carehome(**props):
    from neomodel import adb

    uid = uuid.uuid4().hex
    await adb.cypher_query(
        "CREATE (c:CareHome:Effector {uid: $uid}) SET c += $props",
        {"uid": uid, "props": props},
    )
    return uid


async def test_a_care_home_reports_its_beds(client, neo4j_graph):
    uid = await make_carehome(
        regular_permanent_bed=60, regular_temporary_bed=2, alzheimer_permanent_bed=12,
        alzheimer_temporary_bed=1, uvpha_permanent_bed=6, uhr_permanent_bed=4,
        day_care=8, usld_permanent_bed=10,
    )
    r = await client.get(f"/carehomes/{uid}")
    assert r.status_code == 200
    assert r.json() == {
        "uid": uid, "regular_permanent_bed": 60, "regular_temporary_bed": 2,
        "alzheimer_permanent_bed": 12, "alzheimer_temporary_bed": 1,
        "uvpha_permanent_bed": 6, "uhr_permanent_bed": 4, "day_care": 8,
        "usld_permanent_bed": 10,
    }


async def test_a_bed_count_that_was_never_set_is_zero(client, neo4j_graph):
    """The model's default (IntegerProperty(default=0)) fills a property the node lacks."""
    uid = await make_carehome(regular_permanent_bed=60)
    r = await client.get(f"/carehomes/{uid}")
    assert r.status_code == 200
    body = r.json()
    assert body["regular_permanent_bed"] == 60
    assert body["day_care"] == 0


async def test_an_unknown_care_home_is_not_found(client, neo4j_graph):
    r = await client.get(f"/carehomes/{uuid.uuid4().hex}")
    assert r.status_code == 404


async def test_another_kind_of_effector_is_not_a_care_home(client, neo4j_graph):
    from neomodel import adb

    uid = uuid.uuid4().hex
    await adb.cypher_query("CREATE (:Effector {uid: $uid})", {"uid": uid})
    r = await client.get(f"/carehomes/{uid}")
    assert r.status_code == 404
