from pydantic import BaseModel


class MembershipCategoryPost(BaseModel):
    entry_uid: str
    label: str


class MembershipCategoryPatch(BaseModel):
    label: str | None = None


class MembershipCategoryResponse(BaseModel):
    uid: str
    entry_uid: str
    label: str | None = None
