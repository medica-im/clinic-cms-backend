from datetime import datetime
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


class Invitee(BaseModel):
    uid: str
    email: str | None = None
    name: str | None = None
    createdAt: datetime | None = None
    createdBy: str | None = None
    role: str
    active: bool | None = True
    redeemedAt: int | None = None
