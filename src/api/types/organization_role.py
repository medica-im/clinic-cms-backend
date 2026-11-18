from pydantic import BaseModel


class OrganizationRolePost(BaseModel):
    label: str


class OrganizationRolePatch(BaseModel):
    label: str | None = None


class OrganizationRoleResponse(BaseModel):
    uid: str
    label: str | None = None


class GenderLabels(BaseModel):
    F: str | None = None
    M: str | None = None
    N: str | None = None


class NumberLabels(BaseModel):
    S: GenderLabels = GenderLabels()
    P: GenderLabels = GenderLabels()


OrganizationRoleLabelsResponse = dict[str, NumberLabels]
