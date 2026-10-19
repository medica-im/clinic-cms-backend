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

import api.routers.clone as clone_router

CLEAR = "sync_clear_effector_type_labels_cache"


def calls_in(func) -> set[str]:
    """Names of the functions a function calls, `sync_to_async(f)(...)` included.

    Reads the source rather than calling it: execute_clone needs a Request, a
    peer, a live graph and a token, none of which this assertion is about.
    """
    names = set()
    for node in ast.walk(ast.parse(inspect.getsource(func).lstrip())):
        if not isinstance(node, ast.Call):
            continue
        callees = [node.func, *(node.func.args if isinstance(node.func, ast.Call) else [])]
        names |= {getattr(c, "id", None) or getattr(c, "attr", None) for c in callees}
    return names


def test_the_occupation_labels_are_cleared():
    assert CLEAR in calls_in(clone_router.execute_clone), (
        "/clone/execute does not clear the effector-type labels. A cloned entry "
        "whose occupation is new to this directory will be missing from the "
        "staff listing until the TTL expires, while appearing everywhere else."
    )
