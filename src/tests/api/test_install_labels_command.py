"""`manage.py install_labels` installs the graph's constraints.

neomodel 6 moved install_all_labels and install_labels from the package onto
the `db` singleton; importing them from `neomodel` raises ImportError, so the
command could not even load. It runs here against the scratch database.
"""

import pytest
from django.core.management import call_command
from neomodel import adb

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def constraints():
    rows, _ = await adb.cypher_query("SHOW CONSTRAINTS YIELD labelsOrTypes RETURN labelsOrTypes")
    return {label for (labels,) in rows for label in labels}


async def test_the_command_installs_the_constraints(neo4j_graph):
    from asgiref.sync import sync_to_async

    await sync_to_async(call_command)("install_labels")

    assert {"Entry", "Effector", "Facility"} <= await constraints()
