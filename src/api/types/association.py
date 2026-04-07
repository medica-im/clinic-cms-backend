from pydantic import BaseModel


class OfficerPost(BaseModel):
    entry_uid: str
    effector_uid: str
    role_uid: str
    role_label: str | None = None
    start: str
    stop: str | None = None


class OfficerPatch(BaseModel):
    role_label: str | None = None
    start: str | None = None
    stop: str | None = None


class OfficerResponse(BaseModel):
    uid: str
    entry_uid: str
    effector_uid: str
    role_uid: str
    role_label: str | None = None
    start: str
    stop: str | None = None


class BoardMemberPost(BaseModel):
    entry_uid: str
    effector_uid: str
    category_uid: str | None = None
    start: str
    stop: str | None = None


class BoardMemberPatch(BaseModel):
    start: str | None = None
    stop: str | None = None


class BoardMemberResponse(BaseModel):
    uid: str
    entry_uid: str
    effector_uid: str
    category_uid: str | None = None
    start: str
    stop: str | None = None
