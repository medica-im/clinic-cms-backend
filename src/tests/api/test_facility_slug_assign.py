"""The slug is set when the entry is confirmed, once.

A facility is created without an address: the occupation and the person that
name it best are only known at the end of the entry wizard, which sends the
slug it showed with the entry. Once set, a slug never changes through an entry
(links to /sites/{slug} are shared, and facilities have no redirects), and one
another facility holds is refused with 409, a business rule that applies to a
superuser as much as to anyone.
"""
import pytest
import pytest_asyncio
from fastapi import HTTPException
from neomodel import adb

from directory.facility_slug import assign_facility_slug

TAG = "e2eFacAssign"

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]


@pytest_asyncio.fixture(loop_scope="session")
async def facilities():
    await adb.cypher_query("MATCH (f:Facility) WHERE f.uid STARTS WITH $tag DETACH DELETE f", {"tag": TAG})
    await adb.cypher_query(
        """
        CREATE (:Facility {uid: $tag+'-new', name: 'Zzassign'})
        CREATE (:Facility {uid: $tag+'-set', name: 'Zzassign', slug: 'zzassign-set'})
        CREATE (:Facility {uid: $tag+'-other', name: 'Zzassign', slug: 'zzassign-held'})
        """,
        {"tag": TAG},
    )
    yield
    await adb.cypher_query("MATCH (f:Facility) WHERE f.uid STARTS WITH $tag DETACH DELETE f", {"tag": TAG})


async def slug_of(uid: str) -> str | None:
    rows, _ = await adb.cypher_query("MATCH (f:Facility {uid: $uid}) RETURN f.slug", {"uid": uid})
    return rows[0][0]


async def test_a_facility_without_a_slug_gets_the_one_sent(facilities):
    assert await assign_facility_slug(f"{TAG}-new", "zzassign-chosen") is True
    assert await slug_of(f"{TAG}-new") == "zzassign-chosen"


async def test_a_facility_that_has_one_keeps_it(facilities):
    assert await assign_facility_slug(f"{TAG}-set", "zzassign-other-try") is False
    assert await slug_of(f"{TAG}-set") == "zzassign-set"


async def test_nothing_sent_changes_nothing(facilities):
    assert await assign_facility_slug(f"{TAG}-other", None) is False
    assert await assign_facility_slug(f"{TAG}-other", "  ") is False
    assert await slug_of(f"{TAG}-other") == "zzassign-held"


async def test_a_slug_another_facility_holds_is_a_conflict(facilities):
    with pytest.raises(HTTPException) as refused:
        await assign_facility_slug(f"{TAG}-new", "zzassign-held")
    assert refused.value.status_code == 409
    assert await slug_of(f"{TAG}-new") is None


async def test_a_slug_that_is_not_lowercase_words_and_hyphens_is_refused(facilities):
    with pytest.raises(HTTPException) as refused:
        await assign_facility_slug(f"{TAG}-new", "Zz Assign!")
    assert refused.value.status_code == 422
