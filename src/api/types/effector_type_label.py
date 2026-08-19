from pydantic import BaseModel, RootModel


class GenderedLabels(BaseModel):
    """The three grammatical genders, for one grammatical number.

    Every field is always present, null where no Label row was authored. The
    frontend indexes straight into these (`labels[uid].S.F`) without guarding,
    so an absent key is a TypeError there while a null is simply a blank —
    which is why this is a fixed model rather than a dict.

    The keys are the `code` column of accounts.GrammaticalGender, not names
    invented here: F feminine, M masculine, N neutral.
    """

    F: str | None = None
    M: str | None = None
    N: str | None = None


class NumberedLabels(BaseModel):
    """Singular and plural, each carrying the three genders.

    S and P are the values of directory.models.core.Label.GrammaticalNumber.
    """

    S: GenderedLabels
    P: GenderedLabels


class EffectorTypeLabels(RootModel[dict[str, NumberedLabels]]):
    """The whole response: effector-type uid -> its labels.

    A RootModel because the body is a bare JSON object keyed by uid, with no
    envelope — that is what v1 returned and what the frontend's
    `Record<string, Label>` type expects, so wrapping it in a named field now
    would be a breaking change for no gain.

    Keys are the hex form of the uid (no hyphens), matching how Neo4j node uids
    are stored and how the frontend looks them up.
    """
