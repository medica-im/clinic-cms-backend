"""What a weekly schedule may say, before it reaches the graph.

A day holds zero, one or several periods. Zero means closed, which is why a
day left out of a payload is not an error: a new schedule starts closed, and
the editor only sends the days that were given hours.

A period's end may be 24:00 so that "open all day" and "until midnight" can be
written; its start may not, since a period starting at midnight's end would be
empty. Periods of one day are stored sorted and may touch but not overlap.
"""
import pytest
from pydantic import ValidationError

from api.types.schedule import Period, SchedulePut, periods_from_text, periods_to_text

pytestmark = pytest.mark.no_db

ENTRY = "0123456789abcdef0123456789abcdef"


def schedule(days=None, **overrides):
    payload = {"entry": ENTRY, "channel": "phone", "days": days or {}}
    payload.update(overrides)
    return SchedulePut(**payload)


def p(opens, closes):
    return {"opens": opens, "closes": closes}


@pytest.mark.parametrize("value", ["8:00", "08:0", "0800", "08:60", "24:01", "25:00", "ab:cd", ""])
def test_a_time_must_be_written_hh_mm(value):
    with pytest.raises(ValidationError):
        Period(opens=value, closes="23:00")


def test_a_period_may_end_at_midnight():
    assert Period(opens="00:00", closes="24:00").closes == "24:00"


def test_a_period_may_not_start_at_midnight_s_end():
    with pytest.raises(ValidationError):
        Period(opens="24:00", closes="24:00")


@pytest.mark.parametrize("opens,closes", [("12:00", "12:00"), ("12:00", "08:00")])
def test_a_period_must_end_after_it_starts(opens, closes):
    with pytest.raises(ValidationError):
        Period(opens=opens, closes=closes)


def test_a_day_may_have_one_period():
    assert schedule({1: [p("08:00", "20:00")]}).days[1] == [Period(opens="08:00", closes="20:00")]


def test_a_day_may_have_several_periods():
    s = schedule({1: [p("08:00", "12:00"), p("14:00", "18:00"), p("19:00", "21:00")]})
    assert len(s.days[1]) == 3


def test_periods_of_a_day_are_stored_sorted():
    s = schedule({1: [p("14:00", "18:00"), p("08:00", "12:00")]})
    assert [x.opens for x in s.days[1]] == ["08:00", "14:00"]


def test_periods_of_a_day_may_touch():
    schedule({1: [p("08:00", "12:00"), p("12:00", "18:00")]})


def test_periods_of_a_day_may_not_overlap():
    with pytest.raises(ValidationError):
        schedule({1: [p("08:00", "12:00"), p("11:59", "18:00")]})


def test_a_day_left_out_is_closed():
    s = schedule({1: [p("08:00", "20:00")]})
    assert s.days[2] == [] and s.days[7] == []
    assert sorted(s.days) == [1, 2, 3, 4, 5, 6, 7]


@pytest.mark.parametrize("day", [0, 8, -1])
def test_days_are_numbered_one_to_seven(day):
    with pytest.raises(ValidationError):
        schedule({day: [p("08:00", "12:00")]})


def test_the_json_object_keys_of_a_payload_are_accepted_as_day_numbers():
    s = SchedulePut.model_validate_json(
        '{"entry": "%s", "channel": "phone", "days": {"1": [{"opens": "08:00", "closes": "20:00"}]}}' % ENTRY
    )
    assert s.days[1][0].closes == "20:00"


def test_a_schedule_closes_on_holidays_unless_it_says_otherwise():
    assert schedule().holidays.value == "closed"
    assert schedule(holidays="open").holidays.value == "open"


def test_a_channel_must_be_a_known_one():
    with pytest.raises(ValidationError):
        schedule(channel="fax")


def test_periods_survive_the_round_trip_through_the_graph_text():
    periods = [Period(opens="08:00", closes="12:00"), Period(opens="14:00", closes="24:00")]
    assert periods_to_text(periods) == ["08:00-12:00", "14:00-24:00"]
    assert periods_from_text(periods_to_text(periods)) == periods
    assert periods_from_text(None) == []
