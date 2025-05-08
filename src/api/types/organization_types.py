from pydantic import BaseModel

class OrganizationTypePyNeo(BaseModel):
    element_id_property: str
    uid: str
    name_fr: str
    name_en: str|None
    label_fr: str
    label_en: str|None
    synonyms_fr: list[str]|None
    synonyms_en: list[str]|None

    class Config:       
        fields = {
            'element_id_property': {'exclude':True}, 
            'name_en': {'exclude':True},
            'label_en': {'exclude':True},
            'synonyms_en': {'exclude':True}
        }


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
