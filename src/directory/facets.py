"""Facets of an entry: who it is for, and how to reach it.

Stored on the Entry node (not its type), all optional. Null means unknown,
never "no": the selectors over-include, so a gap in the data drops nobody.
The vocabularies are English identifiers; the labels the page shows are i18n.
"""

CARE_LEVELS = ("emergency", "primary", "secondary", "tertiary", "prevention")
#: Who may contact the service: a patient or a professional with no letter (anyone), a patient
#: with a doctor's letter (referral), or professionals only (a coordination or téléexpertise
#: service). Not Entry.access, which is the least role allowed to see the entry.
WHO_CAN_CONTACT = ("anyone", "referral", "professionals")
#: teleexpertise is, by definition (Code de la santé publique R6316-1), a health professional
#: asking another for an opinion on a patient's case: never a way for the patient to get in, so
#: it fits any who_can_contact.
ACCESS_MODES = ("phone", "walk_in", "appointment", "admission", "online", "teleexpertise", "home_visit")
AUDIENCES = ("students", "caregivers", "parents", "women", "men", "lgbtqia", "older_adults")

#: The names of the facets on the Entry node and in the entry payloads.
ENTRY_FACETS = (
    "age_min",
    "age_max",
    "care_levels",
    "who_can_contact",
    "access_modes",
    "audiences",
    "free",
    "anonymous_care",
)

MAX_AGE = 120


def facets_of(node) -> dict:
    """The facets of an Entry node, null for any it never stored."""
    return {facet: getattr(node, facet, None) for facet in ENTRY_FACETS}


def _whole_years(value, what: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_AGE:
        raise ValueError(f"{what} must be a whole number of years between 0 and {MAX_AGE}")
    return value


def check_age_range(age_min, age_max) -> tuple[int | None, int | None]:
    """Both bounds inclusive, either may be None (open); never reversed."""
    low = _whole_years(age_min, "age_min")
    high = _whole_years(age_max, "age_max")
    if low is not None and high is not None and low > high:
        raise ValueError("age_min must not be above age_max")
    return low, high


def matches_age(age_min: int | None, age_max: int | None, age: int | None) -> bool:
    """Whether a patient of `age` may be served. An unknown age or an open bound matches."""
    if age is None:
        return True
    return (age_min is None or age_min <= age) and (age_max is None or age <= age_max)


def check_choice(value: str | None, vocabulary: tuple[str, ...], what: str) -> str | None:
    if value is not None and value not in vocabulary:
        raise ValueError(f"{what} must be one of {', '.join(vocabulary)}")
    return value


def check_choices(values: list[str] | None, vocabulary: tuple[str, ...], what: str) -> list[str] | None:
    """The words without repeats, in the order of the vocabulary; one unknown word refuses the list."""
    if values is None:
        return None
    for value in values:
        check_choice(value, vocabulary, what)
    return [word for word in vocabulary if word in values]
