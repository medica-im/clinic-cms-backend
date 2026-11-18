"""Every backend knows the same effector types, under the same names.

Effector types are reference data, but each backend's graph was seeded and
edited on its own, so their uids differ. What lets anything written for one
backend (a Label row, a migration, an import mapping) reach the others is that
a type has the same name_fr, and the same other names, everywhere.

Reads the live backends over HTTPS, so it is deselected by default:
run it with `pytest -m backends`.
"""
from collections import defaultdict
from pprint import pformat

import httpx
import pytest

pytestmark = pytest.mark.backends


BACKENDS = {
    "dev": "https://dev.santelyon3.fr",
    "staging": "https://staging.santelyon3.fr",
    "production": "https://santelyon3.fr",
}
NAMES = ("slug_fr", "label_fr", "slug_en", "name_en")


@pytest.fixture(scope="module")
def types() -> dict[str, dict[str, dict]]:
    """{backend: {name_fr: type}}"""
    answer = {}
    for backend, origin in BACKENDS.items():
        response = httpx.get(f"{origin}/api/v2/effector-types", timeout=30)
        response.raise_for_status()
        answer[backend] = {t["name_fr"]: t for t in response.json()}
    return answer


def test_every_backend_has_the_same_types(types):
    every = set().union(*types.values())
    missing = {
        backend: sorted(every - set(by_name))
        for backend, by_name in types.items()
        if every - set(by_name)
    }

    assert not missing, "types some backends lack:\n" + pformat(missing, width=100)


def test_a_type_has_the_same_names_on_every_backend(types):
    every = set().union(*types.values())
    differing = {}
    for name_fr in sorted(every):
        for name in NAMES:
            values = {
                backend: by_name[name_fr].get(name)
                for backend, by_name in types.items()
                if name_fr in by_name
            }
            if len(set(values.values())) > 1:
                differing[f"{name_fr}.{name}"] = values

    assert not differing, "names that differ:\n" + pformat(differing, width=100)


def test_a_mesh_id_names_one_type_on_every_backend(types):
    names = defaultdict(set)
    for by_name in types.values():
        for name_fr, t in by_name.items():
            if t.get("unique_ID"):
                names[t["unique_ID"]].add(name_fr)

    shared_ids = {mesh: sorted(n) for mesh, n in names.items() if len(n) > 1}

    assert not shared_ids, "MeSH ids under several names:\n" + pformat(shared_ids, width=100)
