"""Every serializer that emits `roles` must emit role NAMES, not objects.

The pydantic response types declare `roles` as a list of the Role enum —
"anonymous", "registered", "staff", "administrator", "superuser". A DRF
serializer that lists `roles` in Meta.fields without declaring it as a
SlugRelatedField emits the related objects instead ({"id", "name",
"description"}), and `model_validate` rejects every one of them.

The failure is nastier than a plain 500. The object is written first and the
response is built afterwards, so the row IS created and the client sees only
the error: a person presses Send, nothing happens, presses again, and finds two
records after a reload. That is what happened to POST /api/v2/socialmedia/ —
AsyncSocialNetworkSerializer carried `depth = 2` and no SlugRelatedField, while
the sync SocialNetworkSerializer beside it had one.

Asserted over every serializer in the module rather than the two that were
found broken: the next one added will be covered the day it appears.
"""

import re
import pathlib

import pytest


SOURCE = pathlib.Path(__file__).resolve().parents[2] / "addressbook" / "api" / "serializers.py"


def serializers_emitting_roles() -> list[tuple[str, str]]:
    """(class name, body) for every serializer listing `roles` in its fields."""
    text = SOURCE.read_text(encoding="utf-8")
    found = []
    for match in re.finditer(r"class (\w+Serializer)\(.*?\n(.*?)(?=\nclass |\Z)", text, re.S):
        name, body = match.group(1), match.group(2)
        if "'roles'" in body or '"roles"' in body:
            found.append((name, body))
    return found


def test_the_scan_finds_serializers_at_all():
    """Guard the guard: a regex that matches nothing would pass every test."""
    names = [n for n, _ in serializers_emitting_roles()]
    assert len(names) >= 5, f"only found {names} — the scan is probably broken"


@pytest.mark.parametrize("name,body", serializers_emitting_roles(),
                         ids=lambda v: v if isinstance(v, str) and v.endswith("Serializer") else "")
def test_roles_are_declared_as_names(name, body):
    """`roles` must be a SlugRelatedField over `name`.

    Without it DRF serialises the Role objects, and the pydantic type raises
    "Input should be 'anonymous', 'registered', ... [type=enum,
    input_value={'id': 5, 'name': 'superuser', ...}]" — one error per role, on
    a request whose write has already succeeded.
    """
    assert "SlugRelatedField" in body, (
        f"{name} lists `roles` but does not declare it as a SlugRelatedField, "
        f"so it emits Role objects rather than names and the pydantic response "
        f"type rejects them — after the row has already been written"
    )
    assert re.search(r"slug_field\s*=\s*['\"]name['\"]", body), (
        f"{name} declares roles as a SlugRelatedField but not over `name`"
    )


@pytest.mark.parametrize("name,body", serializers_emitting_roles(),
                         ids=lambda v: v if isinstance(v, str) and v.endswith("Serializer") else "")
def test_depth_does_not_expand_roles(name, body):
    """`depth` expands every relation, which re-introduces the object form.

    AsyncSocialNetworkSerializer had `depth = 2`. An explicit SlugRelatedField
    wins over it, so the two can coexist — but a serializer relying on depth
    alone is the bug, and this says so rather than leaving it to be rediscovered
    from a 500.
    """
    if re.search(r"depth\s*=\s*\d", body):
        assert "SlugRelatedField" in body, (
            f"{name} sets `depth` and lists `roles` without a SlugRelatedField: "
            f"depth expands the Role objects into the payload"
        )
