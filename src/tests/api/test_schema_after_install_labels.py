"""What `manage.py install_labels` leaves in the graph matches the models.

Every `unique_index` property has a uniqueness constraint and every `index`
property an index, under the label of the class that declares or inherits it.
Neo4j 5 has no BTREE index, so on 5 nothing of that type may remain: the
migration from 4.4 converts them, and this is what notices a model that would
bring one back.

Written against the models, so adding a property needs no edit here.
"""
import pytest
from asgiref.sync import sync_to_async
from django.core.management import call_command
from neomodel import adb

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def node_classes():
    import access.neomodels  # noqa: F401
    import directory.models.graph  # noqa: F401
    from neomodel import StructuredNode

    seen, stack = [], list(StructuredNode.__subclasses__())
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        if getattr(cls, "__abstract_node__", False):
            continue
        seen.append(cls)
    return seen


def expected():
    """(label, property) pairs the models ask for, as (uniques, indexes)."""
    uniques, indexes = set(), set()
    for cls in node_classes():
        for name, prop in cls.defined_properties(aliases=False, rels=False).items():
            if getattr(prop, "unique_index", False):
                uniques.add((cls.__label__, name))
            elif getattr(prop, "index", False):
                indexes.add((cls.__label__, name))
    return uniques, indexes


async def major_version():
    rows, _ = await adb.cypher_query("CALL dbms.components() YIELD versions RETURN versions[0]")
    return int(rows[0][0].split(".")[0])


async def installed():
    rows, _ = await adb.cypher_query(
        "SHOW CONSTRAINTS YIELD type, entityType, labelsOrTypes, properties "
        "WHERE type = 'UNIQUENESS' AND entityType = 'NODE' RETURN labelsOrTypes, properties"
    )
    uniques = {(labels[0], props[0]) for labels, props in rows}
    rows, _ = await adb.cypher_query(
        "SHOW INDEXES YIELD type, entityType, labelsOrTypes, properties "
        "WHERE entityType = 'NODE' AND type <> 'LOOKUP' RETURN labelsOrTypes, properties"
    )
    indexes = {(labels[0], props[0]) for labels, props in rows}
    return uniques, indexes


@pytest.fixture
async def installed_graph(neo4j_graph):
    await sync_to_async(call_command)("install_labels")
    return await installed()


async def test_every_unique_property_has_a_constraint(installed_graph):
    uniques, _ = expected()
    missing = sorted(uniques - installed_graph[0])
    assert not missing, f"no uniqueness constraint for {missing}"


async def test_every_indexed_property_has_an_index(installed_graph):
    _, indexes = expected()
    have = installed_graph[1] | installed_graph[0]
    missing = sorted(indexes - have)
    assert not missing, f"no index for {missing}"


async def test_no_btree_index_remains_on_neo4j_5(installed_graph):
    if await major_version() < 5:
        pytest.skip("BTREE is the index type of Neo4j 4.4")
    rows, _ = await adb.cypher_query("SHOW INDEXES YIELD name, type WHERE type = 'BTREE' RETURN name")
    assert rows == []


async def test_installing_twice_changes_nothing(installed_graph):
    await sync_to_async(call_command)("install_labels")
    assert await installed() == installed_graph
