"""A cloned entry gets its Django `Contact` row, not only its graph node.

An entry lives in two places. The graph holds what it *is* — the person, the
occupation, the place, the directory it belongs to. Postgres holds a `Contact`
row, keyed by the entry's uid in `neomodel_uid`, and that row is what emails,
phones, websites and social media links hang off:

    contact = await Contact.objects.aget(neomodel_uid=item.entry)
    except Contact.DoesNotExist:
        raise HTTPException(404, f"Contact {item.entry} not found")

That is `api/routers/emails.py`, and phones, websites and socialmedia each do
the same lookup. So an entry with no Contact row is not partly broken: it is a
complete, correct, visible entry that silently refuses every attempt to give it
contact details, months later, with a 404 naming a table nobody sees in the UI.

The ordinary creation path calls `Contact.objects.acreate(...)` in
`api/serializers/entries.py`. The clone executor writes its Entry with raw
Cypher instead, and Postgres was never part of that contract — so cloning
produced entries that could never be given an email.

Reported from the field: an entry cloned from another instance, reachable at
its own URL and correct in every graph respect, that answered
"Contact ... not found" when a coordinator tried to add their address.
"""
import pytest
import pytest_asyncio
from asgiref.sync import sync_to_async
from neomodel import adb

from addressbook.models import Contact
from api.serializers.clone import execute
from api.types.clone import Resolution

# One loop for the session: `adb` binds its sockets to the loop that opened
# them. django_db because the assertion is about a Postgres row.
pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.integration,
    pytest.mark.django_db,
]

TAG = "e2eCloneContact"

#: Bumped per clone so each one is a different person — the slug generator
#: keeps only candidates no entry holds, and cloning the same person to the
#: same address twice exhausts that list within a session.
_PERSON = 0


def full_entry(**over):
    """A FullEntry-shaped payload, as the source instance would return it."""
    global _PERSON
    _PERSON += 1
    base = {
        "uid": "source-entry-uid",
        "name": f"Camille Clonée{_PERSON}",
        "label": f"Camille Clonée{_PERSON}",
        "slug": f"camille-clonee{_PERSON}",
        "gender": "F",
        "access": "anonymous",
        "carte_vitale": True,
        "effector_type": {"unique_ID": f"{TAG}-UID", "name": "testeur",
                          "slug": f"{TAG}-type-slug", "label": "testeur"},
        "facility": {"name": "Cabinet Cloné", "slug": f"{TAG}-new-fac", "label": ""},
        "address": {"street": "3 Rue Neuve", "zip": "00000", "city": "Clonetown",
                    "building": "", "geographical_complement": "",
                    "longitude": "4.85", "latitude": "45.75", "zoom": 18},
        "payment_methods": [], "third_party_payers": [], "convention": None,
        "memberships": [], "organizations": ["retired-org-node-uid"],
        "rpps": None, "spoken_languages": [],
    }
    base.update(over)
    return base


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def graph():
    await adb.cypher_query(
        "MATCH (n) WHERE n.uid STARTS WITH $tag OR n.slug STARTS WITH $tag "
        "DETACH DELETE n", {"tag": TAG})
    await adb.cypher_query(
        """
        // Both labels, and slug_fr/the department's name: neomodel resolves a
        // node by its full label set and will not resolve one missing a
        // declared property — the slug generator walks this geography.
        CREATE (c:Commune:AdministrativeTerritorialEntityOfFrance {uid:$tag+'-commune', name_fr:'Clonetown', slug_fr:'clonetown',
                           name_en:'Clonetown', slug_en:'clonetown',
                           wikidata:$tag+'-Q1'})
        CREATE (dep:DepartmentOfFrance {uid:$tag+'-dept', name:'Clonedept',
                                        slug:'clonedept', code:'00'})
        CREATE (c)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dep)
        CREATE (org:Entry {uid:$tag+'-org', slug:$tag+'-org', active:true})
        CREATE (d:Directory {uid:$tag+'-dir', name:$tag+'-dir'})
        CREATE (t:EffectorType {uid:$tag+'-type', unique_ID:$tag+'-UID',
                                name_fr:'testeur', slug_fr:$tag+'-type-slug'})
        """,
        {"tag": TAG},
    )
    yield {"org": f"{TAG}-org", "dir": f"{TAG}-dir"}
    # A cloned entry gets a generated uid and slug, so neither carries the tag.
    # The directory edge is what identifies them.
    await adb.cypher_query(
        "MATCH (d:Directory {name:$dir})-[:HAS_ENTRY]->(e:Entry) "
        "OPTIONAL MATCH (e)-[:HAS_EFFECTOR]->(eff:Effector) "
        "OPTIONAL MATCH (e)-[:HAS_FACILITY]->(f:Facility) "
        "DETACH DELETE e, eff, f", {"dir": f"{TAG}-dir"})
    await adb.cypher_query(
        "MATCH (n) WHERE n.uid STARTS WITH $tag OR n.slug STARTS WITH $tag "
        "OR n.creator_directory = $tag+'-dir' DETACH DELETE n", {"tag": TAG})


async def _clone(full, graph, **over):
    res = Resolution(source_uid=full["uid"], effector="create", facility="create", **over)
    return await execute.clone_one(
        full, res, directory_name=graph["dir"], org_uid=graph["org"],
        source_org_entry=None, creator_uid=None,
    )


@sync_to_async
def _contact_count(entry_uid: str) -> int:
    """Contacts carrying this entry's uid.

    `neomodel_uid` is a UUIDField and the graph stores the hex form without
    dashes; Django parses either into the same UUID, so the bare hex the clone
    returns is a valid lookup value.
    """
    return Contact.objects.filter(neomodel_uid=entry_uid).count()


class TestACloneIsReachableFromPostgresToo:
    async def test_the_cloned_entry_has_a_contact_row(self, graph):
        """Without it, emails/phones/websites/socialmedia all 404 on this entry."""
        r = await _clone(full_entry(), graph)
        assert r.status == "created", r.error

        assert await _contact_count(r.entry_uid) == 1, (
            f"cloned entry {r.entry_uid} has no Contact row, so adding an "
            f"email to it answers 'Contact {r.entry_uid} not found'"
        )

    async def test_the_contact_row_is_unique_for_the_entry(self, graph):
        """Two rows for one uid would make `aget` raise MultipleObjectsReturned.

        The contact endpoints fetch with `aget`, which is strict: a duplicate
        turns the 404 into a 500 rather than fixing anything.
        """
        r = await _clone(full_entry(uid="second-source"), graph)
        assert r.status == "created", r.error

        assert await _contact_count(r.entry_uid) == 1
