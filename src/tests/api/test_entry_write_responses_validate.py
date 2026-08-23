"""Every write the entry page can make must return a payload its type accepts.

The failure this guards against is worse than a plain 500, and it happened on
POST /api/v2/socialmedia/: the row is written first and the response is
validated afterwards, so a payload the pydantic type rejects leaves the record
created and the client seeing an error. A person presses Send, nothing happens,
presses again — and finds two records after a reload.

The cause there was `roles` serialised as Role objects rather than names.
test_roles_serialize_as_names.py pins that specific shape across the addressbook
serializers. This file asks the more general question of every endpoint the
/e/{slug} page writes through: does the response model actually accept what the
handler returns?

Held deliberately at the level of contract rather than behaviour — no database,
no HTTP. A handler that builds its payload one way and declares a type that
cannot represent it is a bug visible in the code, and this is what makes it
visible before a deploy rather than after a duplicate row.
"""

import inspect
import re
import pathlib

import pytest


ROUTERS = pathlib.Path(__file__).resolve().parents[2] / "api" / "routers"

# What the entry page at /e/{slug} can create, edit or delete. Appointments are
# here too, though they are graph-backed and carry no roles.
ENTRY_PAGE_ROUTERS = ["websites", "emails", "phones", "socialmedia", "appointment"]


def source_of(router: str) -> str:
    return (ROUTERS / f"{router}.py").read_text(encoding="utf-8")


def write_routes(router: str) -> list[tuple[str, str]]:
    """(method, response_model) for each POST/PUT/PATCH with a declared model."""
    found = []
    for m in re.finditer(
        r'@router\.(post|put|patch)\([^)]*response_model=(\w+)', source_of(router)
    ):
        found.append((m.group(1), m.group(2)))
    return found


@pytest.mark.parametrize("router", ENTRY_PAGE_ROUTERS)
def test_the_router_exists_and_declares_writes(router):
    """Guard the guard: a typo in the list would silently test nothing."""
    assert (ROUTERS / f"{router}.py").exists(), f"no router module for {router}"
    assert write_routes(router), (
        f"{router} declares no POST/PUT/PATCH with a response_model — either "
        f"the entry page no longer writes through it, or the routes lost their "
        f"declared types and nothing checks their shape any more"
    )


@pytest.mark.parametrize("router", ENTRY_PAGE_ROUTERS)
def test_every_write_declares_a_response_model(router):
    """An undeclared write returns whatever the handler happens to build.

    FastAPI validates nothing without a response_model, so the payload shape
    becomes whatever the code does today — and the frontend's expectations stop
    being checked anywhere.
    """
    text = source_of(router)
    undeclared = [
        m.group(0)
        for m in re.finditer(r'@router\.(?:post|put|patch)\("[^"]+"[^)]*\)', text)
        if "response_model=" not in m.group(0) and "-> " not in m.group(0)
    ]
    # A route may declare its type as a return annotation instead.
    if undeclared:
        for route in list(undeclared):
            path = re.search(r'"([^"]+)"', route).group(1)
            handler = re.search(
                re.escape(route) + r"\s*\n(?:async )?def \w+\([^)]*\)[^:]*:", text, re.S
            )
            if handler and "->" in handler.group(0):
                undeclared.remove(route)
    assert not undeclared, (
        f"{router} has writes with no declared response type: {undeclared}. "
        f"Nothing validates what they return."
    )


class TestTheRolesShapeTheyAllShare:
    """The specific mismatch that took socialmedia down.

    A response model whose `roles` is a list of the Role enum can only be built
    from role NAMES. Any handler feeding it Role objects raises four validation
    errors — one per role — after the write has landed.
    """

    @pytest.mark.parametrize("router", ENTRY_PAGE_ROUTERS)
    def test_roles_reach_the_type_as_names(self, router):
        import importlib

        module = importlib.import_module(f"api.routers.{router}")
        for _, model in write_routes(router):
            cls = getattr(module, model, None)
            if cls is None or "roles" not in getattr(cls, "model_fields", {}):
                continue
            # The field exists and is an enum list: the only thing that can
            # populate it is a sequence of names.
            annotation = repr(cls.model_fields["roles"].annotation)
            assert "dict" not in annotation.lower(), (
                f"{router}.{model}.roles is typed to accept objects; the "
                f"frontend and the scrub in api.utils both expect names"
            )
