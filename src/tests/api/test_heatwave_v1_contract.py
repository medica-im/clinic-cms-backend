"""What /api/v1/heatwave/warning/<department>/ answers today.

The frontend shows a heat-wave banner from it (HeatwaveAlert.svelte). The
answer is built from Météo-France's "carte vigilance" feed: the current
canicule colour of one department, if a period covering now is orange or worse.
These tests pin the Django (DRF) implementation so a FastAPI /api/v2 version can
be held to the same contract.

Only the `carte` fixture is tied to the implementation: it stands in for the
upstream feed. Point it at whatever the v2 route fetches through.

Times are built from now, never fixed dates, so a test cannot start failing
because the day it was written has passed.
"""

from datetime import datetime, timedelta, timezone

import pytest
from django.test import Client

URL = "/api/v1/heatwave/warning/{department}/"

CANICULE = 6
HOUR = timedelta(hours=1)


def iso(moment: datetime) -> str:
    return moment.isoformat()


def period(department: str, hazards: list[dict]) -> dict:
    return {"timelaps": {"domain_ids": [{"domain_id": department, "phenomenon_items": hazards}]}}


def hazard(phenomenon_id, color: int, windows: list[tuple[datetime, datetime, int]]) -> dict:
    return {
        "phenomenon_id": phenomenon_id,
        "phenomenon_max_color_id": color,
        "timelaps_items": [
            {"begin_time": iso(begin), "end_time": iso(end), "color_id": ti_color}
            for begin, end, ti_color in windows
        ],
    }


@pytest.fixture
def carte(monkeypatch, site):
    """The upstream feed: `carte(payload)` makes it answer with `payload`,
    `carte(error=True)` makes it fail.

    Depends on `site`: the site middleware looks the request's host up, so a
    request for a host with no Site row never reaches the view.
    """
    import heatwave.utils as utils

    def feed(payload=None, error=False):
        def get():
            if error:
                raise Exception("Error fetching carte data: response.status_code=503")
            return payload

        monkeypatch.setattr(utils, "get_carte_cached", get)

    return feed


def get(department: str, **extra):
    return Client().get(URL.format(department=department), **extra)


@pytest.fixture
def now():
    return datetime.now(timezone.utc)


@pytest.fixture
def clock(monkeypatch):
    """Stops the view's clock, for the tests that sit exactly on a boundary.

    With a moving clock "now" is read twice, a few milliseconds apart, so a
    window ending at the test's now has already ended when the view looks.
    Tied to the implementation like `carte`: it replaces `datetime` in
    heatwave.utils.
    """
    import heatwave.utils as utils

    frozen = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen

    monkeypatch.setattr(utils, "datetime", Frozen)
    return frozen


def active(now, color=3):
    """A canicule alert covering now, for department 69."""
    begin, end = now - HOUR, now + HOUR
    return begin, end, {
        "product": {"periods": [period("69", [hazard(CANICULE, color, [(begin, end, color)])])]}
    }


class TestAnActiveAlert:
    def test_the_answer_is_its_window_and_colour(self, carte, now):
        begin, end, payload = active(now, color=3)
        carte(payload)

        response = get("69")

        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"
        assert response.json() == {
            "start_time": iso(begin),
            "end_time": iso(end),
            "risk_code": "3",
        }

    @pytest.mark.parametrize("color", [2, 3, 4])
    def test_the_risk_code_is_the_colour_as_a_string(self, carte, now, color):
        carte(active(now, color)[2])

        assert get("69").json()["risk_code"] == str(color)

    def test_the_times_are_the_feed_s_own_strings(self, carte, now):
        """Not reformatted: the frontend parses what Météo-France wrote."""
        begin, end = now - HOUR, now + HOUR
        carte({"product": {"periods": [period("69", [hazard(CANICULE, 3, [(begin, end, 3)])])]}})

        body = get("69").json()

        assert body["start_time"] == begin.isoformat()
        assert body["end_time"] == end.isoformat()

    def test_a_phenomenon_id_sent_as_a_string_is_recognised(self, carte, now):
        begin, end = now - HOUR, now + HOUR
        carte({"product": {"periods": [period("69", [hazard("6", 3, [(begin, end, 3)])])]}})

        assert get("69").json()["risk_code"] == "3"

    def test_when_several_windows_cover_now_the_last_one_wins(self, carte, now):
        first = (now - 2 * HOUR, now + 2 * HOUR, 2)
        last = (now - HOUR, now + HOUR, 4)
        carte({"product": {"periods": [period("69", [hazard(CANICULE, 4, [first, last])])]}})

        assert get("69").json() == {
            "start_time": iso(last[0]),
            "end_time": iso(last[1]),
            "risk_code": "4",
        }

    def test_windows_across_periods_are_all_considered(self, carte, now):
        past = (now - 5 * HOUR, now - 4 * HOUR, 3)
        current = (now - HOUR, now + HOUR, 3)
        carte({"product": {"periods": [
            period("69", [hazard(CANICULE, 3, [past])]),
            period("69", [hazard(CANICULE, 3, [current])]),
        ]}})

        assert get("69").json()["start_time"] == iso(current[0])


class TestNoAlert:
    NONE = {"start_time": None, "end_time": None, "risk_code": None}

    def test_green_is_no_alert(self, carte, now):
        """Colour 1 means nothing to report, even with a window covering now."""
        carte(active(now, color=1)[2])

        assert get("69").json() == self.NONE

    def test_an_alert_that_has_not_started_is_not_reported(self, carte, now):
        window = (now + HOUR, now + 2 * HOUR, 3)
        carte({"product": {"periods": [period("69", [hazard(CANICULE, 3, [window])])]}})

        assert get("69").json() == self.NONE

    def test_an_alert_that_has_ended_is_not_reported(self, carte, now):
        window = (now - 2 * HOUR, now - HOUR, 3)
        carte({"product": {"periods": [period("69", [hazard(CANICULE, 3, [window])])]}})

        assert get("69").json() == self.NONE

    def test_the_end_of_a_window_is_exclusive(self, carte, clock):
        window = (clock - HOUR, clock, 3)
        carte({"product": {"periods": [period("69", [hazard(CANICULE, 3, [window])])]}})

        assert get("69").json() == self.NONE

    def test_the_start_of_a_window_is_inclusive(self, carte, clock):
        window = (clock, clock + HOUR, 3)
        carte({"product": {"periods": [period("69", [hazard(CANICULE, 3, [window])])]}})

        assert get("69").json()["start_time"] == iso(clock)

    def test_a_window_that_is_green_inside_an_orange_phenomenon_is_skipped(self, carte, now):
        """The phenomenon peaks orange later; the window covering now is green."""
        green_now = (now - HOUR, now + HOUR, 1)
        orange_later = (now + 2 * HOUR, now + 3 * HOUR, 3)
        carte({"product": {"periods": [period("69", [hazard(CANICULE, 3, [green_now, orange_later])])]}})

        assert get("69").json() == self.NONE

    def test_another_phenomenon_is_not_a_heat_wave(self, carte, now):
        begin, end = now - HOUR, now + HOUR
        wind = 1
        carte({"product": {"periods": [period("69", [hazard(wind, 3, [(begin, end, 3)])])]}})

        assert get("69").json() == self.NONE

    def test_another_department_s_alert_is_not_ours(self, carte, now):
        carte(active(now)[2])

        assert get("13").json() == self.NONE

    @pytest.mark.parametrize("payload", [{}, {"product": {}}, {"product": {"periods": []}}, None])
    def test_an_empty_feed_is_no_alert(self, carte, payload):
        carte(payload)

        response = get("69")

        assert response.status_code == 200
        assert response.json() == self.NONE

    def test_the_corsican_codes_are_departments_too(self, carte, now):
        begin, end = now - HOUR, now + HOUR
        carte({"product": {"periods": [period("2A", [hazard(CANICULE, 3, [(begin, end, 3)])])]}})

        assert get("2A").json()["risk_code"] == "3"


class TestWhenTheFeedFails:
    def test_the_answer_is_a_404_with_no_body(self, carte):
        carte(error=True)

        response = get("69")

        assert response.status_code == 404
        assert response.content == b""


class TestTheRoute:
    def test_it_is_served_without_a_login(self, carte, now):
        carte(active(now)[2])

        assert get("69").status_code == 200

    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    def test_it_only_reads(self, carte, now, method):
        carte(active(now)[2])

        response = getattr(Client(), method)(URL.format(department="69"))

        assert response.status_code == 405
        assert set(response["Allow"].replace(" ", "").split(",")) == {"GET", "HEAD", "OPTIONS"}

    def test_the_url_needs_its_trailing_slash(self, carte, now):
        carte(active(now)[2])

        response = Client().get("/api/v1/heatwave/warning/69")

        assert response.status_code == 301
        assert response["Location"] == "/api/v1/heatwave/warning/69/"
