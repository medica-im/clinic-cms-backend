from pydantic import BaseModel, Field

class OrganizationTypePyNeo(BaseModel):
    element_id_property: str = Field(exclude=True)
    uid: str
    name_fr: str
    name_en: str|None = Field(exclude=True)
    label_fr: str
    label_en: str|None = Field(exclude=True)
    synonyms_fr: list[str]|None
    synonyms_en: list[str]|None = Field(exclude=True)

class OrganizationTypePy(BaseModel):
    uid: str
    name_fr: str
    label_fr: str
    synonyms_fr: list[str]
    organization_type: str | None

organization_type_exclude_keys = {
    'element_id_property': True,
    'name_en': True,
    'label_en': True,
    'synonyms_en': True
}
