from pydantic import BaseModel

class OrganizationTypePyNeo(BaseModel):
    element_id_property: str
    uid: str
    name_fr: str
    name_en: str
    label_fr: str
    label_en: str
    synonyms_fr: list[str]
    synonyms_en: list[str]

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
