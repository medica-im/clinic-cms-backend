"""A clone can bring an occupation this directory has never listed.

That is usually the *point* of cloning: the person is new here, and so is what
they do. The home page's staff listing does not read the occupation from the
entry — `cardCatEntries` groups entries by effector type and then asks
`genderedLabel` for its name, which comes from `/api/v2/effector-type-labels`.

So a clone that drops `v2:entries` but leaves the labels cached puts the entry
everywhere except the one component that names professions: the group is simply
absent from the home page while the entry itself is visible in the directory,
on its own page and on the map. That is a confusing way to discover a cache was
missed, which is why it is pinned here.

Reported from the field: "her profession didn't exist on dev, and I can't see
the profession in the staff listing component."
"""
import ast
import inspect

import pytest

import api.routers.clone as clone_router

# Both twins. The v2 endpoint is keyed by site; the v1 DRF one is keyed by
# language, so the site fan-out in clear_cache does not reach it and it has to
# be named separately.
LABEL_CACHES = ["v2:effector-type-labels", "v1:effector_type_labels"]


def cleared_by(func) -> list[str]:
    """Endpoint names handed to any cache-clearing call in the function.

    Reads the source rather than calling it: execute_clone needs a Request, a
    peer, a live graph and a token, none of which this assertion is about.

    Handles `sync_to_async(sync_clear_cache)("...")` as well as a direct call —
    the v1 clear has to be wrapped, and a helper that only recognised the plain
    form would report the cache as uncleared when it is.
    """
    tree = ast.parse(inspect.getsource(func).lstrip())
    cleared = []

    def names_a_clear(node: ast.Call) -> bool:
        f = node.func
        direct = getattr(f, "id", None) or getattr(f, "attr", None)
        if direct in ("clear_cache", "sync_clear_cache"):
            return True
        # sync_to_async(sync_clear_cache)(...) — the name is in the callee.
        if isinstance(f, ast.Call):
            for a in f.args:
                if (getattr(a, "id", None) or getattr(a, "attr", None)) in (
                    "clear_cache", "sync_clear_cache"
                ):
                    return True
        return False

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not names_a_clear(node):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                cleared.append(arg.value)
                break
    return cleared


@pytest.mark.parametrize("endpoint", LABEL_CACHES)
def test_the_occupation_labels_are_cleared(endpoint):
    cleared = cleared_by(clone_router.execute_clone)
    assert endpoint in cleared, (
        f"/clone/execute does not clear {endpoint!r}. A cloned entry whose "
        f"occupation is new to this directory will be missing from the staff "
        f"listing until the TTL expires, while appearing everywhere else. "
        f"It clears {cleared}."
    )
