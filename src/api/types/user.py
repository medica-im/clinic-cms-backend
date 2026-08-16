from pydantic import BaseModel


class AccountOut(BaseModel):
    uid: str
    iss: str | None = None
    sub: str
    createdAt: int | None = None


class AccessOut(BaseModel):
    uid: str
    role: str
    createdAt: int | None = None
    active: bool | None = True
    # Whether this access is usable right now, which is a separate question
    # from whether it is the current one. A suspended access stays active so
    # the identity and the role survive — the dashboard needs both to say why
    # nothing works.
    suspendedAt: int | None = None
    suspensionReason: str | None = None


class AccessHistoryOut(BaseModel):
    """One Access a user has held, current or superseded.

    The superseded ones are the audit trail: a role is never edited in place,
    so each past role is still here with the time it ended and who ended it.
    `createdByRole` is what the actor held when they made the change, recorded
    at the time rather than resolved on read.
    """
    uid: str
    role: str
    active: bool | None = True
    createdAt: int | None = None
    createdBy: str | None = None
    createdByName: str | None = None
    createdByRole: str | None = None
    supersededAt: int | None = None
    supersededBy: str | None = None
    suspendedAt: int | None = None
    suspensionReason: str | None = None


class RoleChangeIn(BaseModel):
    role: str


class SuspensionIn(BaseModel):
    reason: str | None = None


class User(BaseModel):
    uid: str
    email: str | None = None
    name: str | None = None
    createdAt: int | None = None
    accounts: list[AccountOut] = []
    access: list[AccessOut] = []


class UserMeOut(BaseModel):
    uid: str
    name: str | None = None
    email: str | None = None
    picture: str | None = None
    role: str | None = None
    gender: str | None = None
    effector: str | None = None
    full_name: str | None = None
    # A suspended user keeps their identity and loses their role, so `role`
    # alone cannot tell them apart from somebody who was never granted
    # anything. The dashboard needs the difference to explain itself.
    suspended: bool = False
    suspensionReason: str | None = None


class ListmonkExportRequest(BaseModel):
    user_uids: list[str]
