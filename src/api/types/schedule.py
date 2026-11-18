import re
from enum import Enum

from pydantic import BaseModel, field_validator

DAYS = range(1, 8)
TIME = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class Channel(str, Enum):
    ON_SITE = "on_site"
    PHONE = "phone"
    SMS = "sms"
    ONLINE = "online"


class Holidays(str, Enum):
    CLOSED = "closed"
    OPEN = "open"


def minutes(time: str) -> int:
    hours, mins = time.split(":")
    return int(hours) * 60 + int(mins)


class Period(BaseModel):
    opens: str
    closes: str

    @field_validator("opens")
    @classmethod
    def _opens_is_a_time(cls, value: str) -> str:
        if not TIME.match(value):
            raise ValueError("opens must be written HH:MM")
        return value

    @field_validator("closes")
    @classmethod
    def _closes_is_a_time_or_midnight(cls, value: str) -> str:
        if value != "24:00" and not TIME.match(value):
            raise ValueError("closes must be written HH:MM, or 24:00")
        return value

    @field_validator("closes")
    @classmethod
    def _closes_after_opens(cls, value: str, info) -> str:
        opens = info.data.get("opens")
        if opens is not None and minutes(value) <= minutes(opens):
            raise ValueError("closes must be after opens")
        return value


class SchedulePut(BaseModel):
    entry: str
    channel: Channel
    label: str | None = None
    holidays: Holidays = Holidays.CLOSED
    days: dict[int, list[Period]] = {}

    @field_validator("days")
    @classmethod
    def _seven_sorted_days(cls, days: dict[int, list[Period]]) -> dict[int, list[Period]]:
        unknown = [day for day in days if day not in DAYS]
        if unknown:
            raise ValueError(f"days are numbered 1 to 7, got {unknown}")
        week: dict[int, list[Period]] = {}
        for day in DAYS:
            periods = sorted(days.get(day, []), key=lambda period: minutes(period.opens))
            for earlier, later in zip(periods, periods[1:]):
                if minutes(later.opens) < minutes(earlier.closes):
                    raise ValueError(f"day {day}: periods overlap")
            week[day] = periods
        return week


class SchedulePost(SchedulePut):
    pass


class Schedule(SchedulePut):
    uid: str


def periods_to_text(periods: list[Period]) -> list[str]:
    return [f"{period.opens}-{period.closes}" for period in periods]


def periods_from_text(texts: list[str] | None) -> list[Period]:
    return [Period(opens=text[:5], closes=text[6:]) for text in texts or []]


def node_properties(schedule: SchedulePut) -> dict:
    properties: dict = {
        "channel": schedule.channel.value,
        "label": schedule.label,
        "holidays": schedule.holidays.value,
    }
    for day in DAYS:
        properties[f"day_{day}"] = periods_to_text(schedule.days[day])
    return properties


def schedule_from_node(entry: str, node: dict) -> Schedule:
    return Schedule(
        uid=node["uid"],
        entry=entry,
        channel=node["channel"],
        label=node.get("label"),
        holidays=node.get("holidays", Holidays.CLOSED.value),
        days={day: periods_from_text(node.get(f"day_{day}")) for day in DAYS},
    )
