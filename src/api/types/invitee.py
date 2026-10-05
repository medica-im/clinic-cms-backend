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
    sent: the mail service accepted it. failed: refused (errorKind says what
    kind of failure, error the service's words), or queued and never settled
    (timedOut: the page gives that reason itself). delivered / deferred /
    bounced / complained come from the service's events; suppressed: not sent,
    the address is on the do-not-send list."""

    status: Literal["queued", "sent", "delivered", "deferred", "bounced", "complained", "suppressed", "failed"]
    at: datetime
    errorKind: str | None = None
    error: str | None = None
    timedOut: bool = False

    @classmethod
    def from_row(cls, row) -> "EmailDelivery":
        from mailer.delivery import delivery_status, timed_out
        return cls(
            status=delivery_status(row),
            at=row.updated,
            errorKind=getattr(row, "error_kind", "") or None,
            error=row.error or None,
            timedOut=timed_out(row),
        )


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
