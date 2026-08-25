"""A clone has to drop this instance's cached payloads.

Cloning writes an entry, and usually a facility, straight into the graph — it
does not go through create_entry or create_facility, which clear their own
caches. So the clone endpoint has to do it, or the new entry is absent from
every cached view until the TTL expires:

    v2:entries              the directory listing and the map
    v1:facilities           the facility list
    v2:public/facilities    the public facility record behind /sites/{slug}

The failure is quiet and confusing: the results screen links to /e/{slug}, that
page works because it is fetched by uid, and the entry is simply missing from
the annuaire the superuser looks at next.

Asserted against the source rather than a live cache, like
test_facility_edit_clears_the_entries_cache.py — what matters is which caches
the code drops, and that is visible in the call itself.
"""
import ast
import inspect

import pytest

import api.routers.clone as clone_router

# Every cached payload a cloned entry appears in.
CLONE_CACHES = ["v2:entries", "v1:facilities", "v2:public/facilities"]


def cleared_by(func) -> list[str]:
    tree = ast.parse(inspect.getsource(func).lstrip())
    cleared = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name != "clear_cache":
            continue
        if node.args and isinstance(node.args[0], ast.Constant):
            cleared.append(node.args[0].value)
    return cleared


@pytest.mark.parametrize("endpoint", CLONE_CACHES)
def test_executing_a_clone_clears_the_cache(endpoint):
    cleared = cleared_by(clone_router.execute_clone)
    assert endpoint in cleared, (
        f"/clone/execute does not clear {endpoint!r}, so a cloned entry stays "
        f"missing from that payload until the TTL expires. It clears {cleared}."
    )


def test_the_caches_are_cleared_once_for_the_batch_not_per_entry():
    """Each clear_cache call walks every Role x Directory key for the site.

    Doing that inside the per-entry loop would repeat the whole fan-out for a
    fifty-entry batch, for no benefit — the last clear is the only one that
    matters.
    """
    source = inspect.getsource(clone_router.execute_clone)
    tree = ast.parse(source.lstrip())
    fn = tree.body[0]

    def clears_in(node) -> int:
        return sum(
            1
            for n in ast.walk(node)
            if isinstance(n, ast.Call)
            and (getattr(n.func, "id", None) or getattr(n.func, "attr", None)) == "clear_cache"
        )

    in_loops = sum(clears_in(n) for n in ast.walk(fn) if isinstance(n, (ast.For, ast.AsyncFor)))
    assert in_loops == 0, (
        "clear_cache is called inside the per-entry loop; each call fans out "
        "over every role and directory, so a batch would repeat it needlessly"
    )
    assert clears_in(fn) == len(CLONE_CACHES)
