"""A facility without a BAN id stores null, never an empty string.

The facility forms send their hidden ban_id/ban_banId inputs as "" when the
geocoder was not used, and the API stored that: on dev, 36 facilities held ""
next to 160 holding null, two spellings of "no id". One spelling keeps queries
for missing ids honest (`IS NULL`), which the planned BAN repair relies on.
"""
import uuid

import pytest

from api.types.facility import FacilityPost, FacilityPut

BAN_ID = "84007_5020_00001"
BAN_BANID = "93507b74-65da-4da8-8028-74ff47dbe1d4"

BASE = {
    "name": "Cabinet", "label": None, "slug": "cabinet", "building": None,
    "street": "1 Rue Piot", "geographical_complement": None, "zip": "84270",
}


def put(**ids) -> FacilityPut:
    return FacilityPut(**BASE, **ids)


def post(**ids) -> FacilityPost:
    return FacilityPost(**BASE, commune=uuid.uuid4().hex, **ids)


@pytest.mark.parametrize("build", [put, post], ids=["put", "post"])
class TestTheBanIds:
    @pytest.mark.parametrize("blank", ["", "  ", None])
    def test_a_blank_id_is_stored_as_null(self, build, blank):
        f = build(ban_id=blank, ban_banId=blank)
        assert (f.ban_id, f.ban_banId) == (None, None)

    def test_real_ids_are_kept(self, build):
        f = build(ban_id=BAN_ID, ban_banId=BAN_BANID)
        assert (f.ban_id, f.ban_banId) == (BAN_ID, BAN_BANID)
