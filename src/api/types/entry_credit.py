from pydantic import BaseModel


class CreditedType(BaseModel):
    name: str
    label: str | None


class CreditAvatar(BaseModel):
    sm: str | None = None
    lg: str | None = None
    raw: str | None = None


class EntryCredit(BaseModel):
    """How a page credits a team member: who, in what occupation — not a profile."""

    entrySlug: str
    name: str
    effector_type: CreditedType
    active: bool
    avatar: CreditAvatar | None
