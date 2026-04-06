from pydantic import BaseModel


class OrganizationRolePost(BaseModel):
    label: str


class OrganizationRolePatch(BaseModel):
    label: str | None = None


class OrganizationRoleResponse(BaseModel):
    uid: str
    label: str | None = None
