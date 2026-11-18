"""Moving a facility on the map must drop the cached entries.

An entry's coordinates are served twice, from two caches:

    /api/v2/public/facilities   the facility's own record
    /api/v2/entries             every entry, each carrying address.latitude
                                and address.longitude for its facility

The map on the directory reads the second — createEntriesMapData in
src/lib/components/Map/mapData.ts plots entry.address.latitude/longitude — so
correcting a facility's GPS in the edit modal on /sites/{slug} has to invalidate
`v2:entries` as well as the facility caches. Clearing only the facility ones
leaves every pin on the annuaire at the old position until the entries TTL
expires, while the facility page itself shows the new one: the same coordinates,
two answers, for as long as the cache lives.

avatar.py already does this — three writes there each clear "v2:entries" for the
same reason, an avatar being another field the entries payload carries.

The assertions are on the endpoint strings passed to clear_cache rather than on
redis, so they run without a cache server and name what is missing when they
fail.
"""

import ast
import inspect

import pytest

import api.serializers.facility as facility_serializers


# The three payloads a facility's coordinates reach. `v2:entries` is the one
# that was missing, and the one the map reads.
FACILITY_CACHES = ["v1:facilities", "v2:public/facilities"]
ENTRIES_CACHE = "v2:entries"


def cleared_by(func) -> list[str]:
    """The literal endpoint strings the function hands to clear_cache.

    Read from the source rather than by calling it: update_facility needs a
    Request, a live graph and a facility node, none of which this assertion is
    about. What matters is which caches the code drops, and that is visible in
    the call itself.
    """
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


class TestUpdatingAFacilityClearsTheEntries:
    """The edit modal on /sites/{slug} — PUT /api/v2/facilities/{uid}."""

    def test_the_entries_cache_is_cleared(self):
        cleared = cleared_by(facility_serializers.update_facility)

        assert ENTRIES_CACHE in cleared, (
            "update_facility does not clear the entries cache, so a facility "
            "moved on the map keeps its old coordinates on the directory until "
            f"the TTL expires. It clears {cleared}. The entries payload carries "
            "address.latitude and address.longitude per entry, which is what "
            "createEntriesMapData plots."
        )

    @pytest.mark.parametrize("endpoint", FACILITY_CACHES)
    def test_the_facility_caches_are_still_cleared(self, endpoint):
        """The existing behaviour, so adding the entries clear does not lose it."""
        assert endpoint in cleared_by(facility_serializers.update_facility)


class TestCreatingAFacilityClearsTheEntries:
    """Creating one places a pin just as moving one does.

    A facility created with coordinates appears on the map through the same
    entries payload, so it needs the same invalidation. Covered here because
    the two functions sit side by side and only one was ever changed.
    """

    def test_the_entries_cache_is_cleared(self):
        cleared = cleared_by(facility_serializers.create_facility)

        assert ENTRIES_CACHE in cleared, (
            "create_facility does not clear the entries cache: a new facility "
            f"is missing from the map until the TTL expires. It clears {cleared}."
        )

    @pytest.mark.parametrize("endpoint", FACILITY_CACHES)
    def test_the_facility_caches_are_still_cleared(self, endpoint):
        assert endpoint in cleared_by(facility_serializers.create_facility)


class TestTheMapReadsWhatTheseCachesHold:
    """Why `v2:entries` belongs in the list at all.

    If the entries payload ever stops carrying per-entry coordinates, this
    file's premise is gone and the extra invalidation is just cost. Pinning the
    field means that change fails here, where the reason is written down, rather
    than silently leaving a redundant cache drop behind.
    """

    def test_an_entry_carries_its_facility_coordinates(self):
        # allentry, singular: the module behind GET /entries.
        from api.types.allentry import Entry

        address = Entry.model_fields["address"].annotation
        fields = getattr(address, "model_fields", {})

        assert "latitude" in fields and "longitude" in fields, (
            "the entries payload no longer carries per-entry coordinates; if "
            "the map no longer reads them, update_facility need not clear "
            "v2:entries and this file can go"
        )
