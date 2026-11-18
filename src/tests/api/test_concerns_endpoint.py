"""GET /concerns: the selector's tree for one directory.

The directory is the site's own unless `?directory=` names a sibling, and it is
listed under the same rule as its entries: a reserved directory's tree is as
reserved as its list. The graph semantics are pinned in test_concerns.py.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.routers.concerns import list_concerns

pytestmark = pytest.mark.asyncio

TREE = [
    {
        "uid": "c1",
        "slug": "addictions",
        "name": "Addictions",
        "kind": "chapter",
        "parent": None,
        "synonyms": [],
        "entries": ["e1"],
        "see_also": [],
    }
]


def served(role, minimum, tree=TREE):
    directory = SimpleNamespace(name="sm", site=SimpleNamespace())
    return (
        patch("api.routers.concerns.resolve_directory", AsyncMock(return_value=(directory, minimum))),
        patch("api.routers.concerns.get_neo4j_role", AsyncMock(return_value=role)),
        patch("api.routers.concerns.concerns_of_directory", AsyncMock(return_value=tree)),
    )


async def call(role, minimum, directory=None):
    a, b, c = served(role, minimum)
    with a, b, c as concerns:
        result = await list_concerns(SimpleNamespace(), None, directory)
        return result, concerns


async def test_an_open_directory_gives_its_tree_to_anyone():
    result, concerns = await call(None, "anonymous")
    assert [c["slug"] for c in result] == ["addictions"]
    concerns.assert_awaited_once()
    assert concerns.await_args.args[0] == "sm"


@pytest.mark.parametrize("role", [None, "registered", "anonymous"])
async def test_a_reserved_directory_is_closed_to_the_public(role):
    with pytest.raises(HTTPException) as refused:
        await call(role, "staff")
    assert refused.value.status_code == 403


@pytest.mark.parametrize("role", ["staff", "administrator", "superuser"])
async def test_a_reserved_directory_opens_to_its_roles(role):
    result, _ = await call(role, "staff")
    assert len(result) == 1


async def test_the_directory_param_is_passed_to_the_resolver():
    a, b, c = served(None, "anonymous")
    with a as resolve, b, c:
        await list_concerns(SimpleNamespace(), None, "cpts-lyon-3-sante-mentale")
    assert resolve.await_args.args[1] == "cpts-lyon-3-sante-mentale"
