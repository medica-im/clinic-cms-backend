from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr


class InviteePost(BaseModel):
    email: EmailStr
    role: str
    name: str | None = None
    entry: str


class InviteeListmonkExportRequest(BaseModel):
    invitee_uids: list[str]


class InviteePatch(BaseModel):
    email: EmailStr | None = None
    role: str | None = None
    name: str | None = None
    active: bool | None = None


class EmailDelivery(BaseModel):
    """The latest attempt at sending an invitation's email (mailer.delivery).
    sent: Mailgun accepted it. failed: refused (error says why), or queued and
    never settled (timedOut: the page gives that reason itself)."""

    status: Literal["queued", "sent", "failed"]
    at: datetime
    error: str | None = None
    timedOut: bool = False


class Invitee(BaseModel):
    uid: str
    email: str | None = None
    name: str | None = None
    createdAt: datetime | None = None
    createdBy: str | None = None
    role: str
    active: bool | None = True
    redeemedAt: int | None = None
    # None: no recorded attempt (created before recording, or never emailed).
    emailDelivery: EmailDelivery | None = None
