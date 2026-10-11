"""What the entry lookup and the entry list return for each collected column.

get_uid_query and get_entries_query collect lists (directories, memberships,
tags, ...). neomodel 5 handed each back wrapped in one more list, which the
code unwrapped; neomodel 6 hands them back as Cypher built them. Whatever
neomodel does, the entry page and the directory listing must get flat lists of
the same things, so this pins them on an entry where every list has something
in it.
"""

from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async
from neomodel import adb

from directory.utils import async_find_entry, find_entry, get_entries, sync_get_entries

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

ENTRY, ORG = "e" * 32, "0" * 32
CREATOR, OWNER = "c" * 32, "d" * 32


@pytest.fixture
async def entry(neo4j_graph):
    await adb.cypher_query(
        """
        CREATE (country:Country {uid: $country, name_fr: 'France'})
        CREATE (dpt:DepartmentOfFrance {uid: $dpt, name: 'Rhône', code: '69', slug: 'rhone', wikidata: 'Q46130'})
        CREATE (c:AdministrativeTerritorialEntityOfFrance:Commune {uid: $commune, name_fr: 'Lyon', slug_fr: 'lyon'})
        CREATE (f:Facility {uid: $facility, slug: 'cabinet-lafayette', name: 'Cabinet Lafayette'})
        CREATE (parent:EffectorType {uid: $parent, name_fr: 'soignant', label_fr: 'soignant', synonyms_fr: [],
                                     definition_fr: '', slug_fr: 'soignant'})
        CREATE (et:EffectorType:HCW {uid: $type, name_fr: 'infirmier', label_fr: 'infirmier', synonyms_fr: [],
                                     definition_fr: '', slug_fr: 'infirmier'})
        CREATE (e:Effector {uid: $effector, name_fr: 'Jean Dupont', creator_directory: 'lyon'})
        CREATE (entry:Entry {uid: $entry, slug: 'dupont-jean-infirmier-69', active: true,
                             payment: ['Carte bancaire'], third_party_payer: ['CPAM']})
        CREATE (org:Entry {uid: $org, slug: 'cpts-lyon-3', active: true})
        CREATE (:PaymentMethod {name: 'Carte bancaire'}), (:ThirdPartyPayer {name: 'CPAM'})
        CREATE (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (c)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt)
        CREATE (dpt)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(country)
        CREATE (et)-[:IS_A]->(parent)
        CREATE (entry)-[:HAS_FACILITY]->(f), (entry)-[:HAS_EFFECTOR]->(e), (entry)-[:HAS_EFFECTOR_TYPE]->(et)
        CREATE (:Directory {name: 'lyon'})-[:HAS_ENTRY]->(entry)
        CREATE (:Directory {name: 'rhone'})-[:HAS_ENTRY]->(entry)
        CREATE (entry)-[:MEMBER_OF]->(org)
        CREATE (et)-[:HAS_TAG_CATEGORY]->(tc:TagCategory {label: 'Pratiques'})
        CREATE (entry)<-[:TAGS]-(:Tag {uid: 'tag-plaies', label: 'Plaies'})-[:IS_A]->(tc)
        CREATE (entry)-[:CREATED_BY]->(:User {uid: $creator})
        CREATE (entry)-[:OWNED_BY]->(:User {uid: $owner})
        CREATE (entry)-[:HAS_APPOINTMENT]->(:Appointment:Office {uid: $appointment, url: 'https://rdv.example.org'})
        """,
        {"country": "1" * 32, "dpt": "2" * 32, "commune": "3" * 32, "facility": "4" * 32,
         "parent": "5" * 32, "type": "6" * 32, "effector": "7" * 32, "entry": ENTRY, "org": ORG,
         "creator": CREATOR, "owner": OWNER, "appointment": "8" * 32},
    )


def collected(found, directory=lambda d: d.name):
    """Each collected column, reduced to what identifies its items."""
    return {
        "directories": sorted(directory(d) for d in found["directories"]),
        "memberships": [m.uid for m in found["memberships"]],
        "tags": [t.uid for t in found["tags"]],
        "tagcats": [t.label for t in found["tagcats"]],
        "creator_uids": found["creator_uids"],
        "owner_uids": found["owner_uids"],
        "third_party_payers": [p.name for p in found["third_party_payers"]],
        "payment_methods": [p.name for p in found["payment_methods"]],
        "effector_type_labels": sorted(found["effector_type_labels"]),
        "appointments": len(found["appointments"]),
    }


EXPECTED = {
    "directories": ["lyon", "rhone"],
    "memberships": [ORG],
    "tags": ["tag-plaies"],
    "tagcats": ["Pratiques"],
    "creator_uids": [CREATOR],
    "owner_uids": [OWNER],
    "third_party_payers": ["CPAM"],
    "payment_methods": ["Carte bancaire"],
    "effector_type_labels": ["EffectorType", "HCW"],
    "appointments": 1,
}


async def test_async_find_entry(entry):
    assert collected(await async_find_entry(uid=ENTRY)) == EXPECTED


async def test_find_entry(entry):
    """The sync lookup hands directories back as their names."""
    found = await sync_to_async(find_entry)(uid=ENTRY)
    assert collected(found, directory=lambda name: name) == EXPECTED


def listed(rows):
    """The listing's collected columns; memberships are already uids there."""
    [row] = rows
    return {
        "uid": row["entry"].uid,
        "directories": sorted(d.name for d in row["directories"]),
        "memberships": row["memberships"],
        "tags": [t.uid for t in row["tags"]],
        "tagcats": [t.label for t in row["tagcats"]],
        "creator_uids": row["creator_uids"],
        "owner_uids": row["owner_uids"],
    }


LISTED = {
    "uid": ENTRY,
    "directories": ["lyon", "rhone"],
    "memberships": [ORG],
    "tags": ["tag-plaies"],
    "tagcats": ["Pratiques"],
    "creator_uids": [CREATOR],
    "owner_uids": [OWNER],
}

LYON = SimpleNamespace(name="lyon")


async def test_get_entries(entry):
    assert listed(await get_entries(LYON)) == LISTED


async def test_sync_get_entries(entry):
    assert listed(await sync_to_async(sync_get_entries)(LYON)) == LISTED
