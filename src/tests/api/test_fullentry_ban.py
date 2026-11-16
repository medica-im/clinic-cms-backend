"""The full entry carries its facility's BAN ids, so a clone keeps them.

The clone's preflight and execute read `ban_id` and `ban_banId` from the full entry:
preflight to recognise the same building here (an exact BAN match reuses it without
asking), execute to write them on a facility it creates. The payload never carried
them, so every facility cloned from dev to staging arrived without a BAN id, and
none could ever match by BAN.
"""
from types import SimpleNamespace

from api.serializers.fullentry import facility_ban
from api.types.fullentry import FullEntry


def test_the_facility_ban_ids_are_read_from_the_facility_node():
    facility = SimpleNamespace(ban_id="69387_3745_00164", ban_banId="1e2bed1d-e76d-4a07-b9a3-e95b48913655")
    assert facility_ban(facility) == {
        "ban_id": "69387_3745_00164", "ban_banId": "1e2bed1d-e76d-4a07-b9a3-e95b48913655",
    }


def test_a_facility_without_ban_ids_gives_none():
    assert facility_ban(SimpleNamespace()) == {"ban_id": None, "ban_banId": None}


def test_the_response_model_does_not_drop_them():
    """The route answers through FullEntry, which drops any field it does not declare."""
    assert {"ban_id", "ban_banId"} <= set(FullEntry.model_fields)
