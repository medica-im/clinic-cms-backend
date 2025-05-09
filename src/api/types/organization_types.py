from pydantic import BaseModel, Field

class OrganizationTypePy(BaseModel):
    element_id_property: str = Field(exclude=True)
    uid: str
    name_fr: str
    name_en: str|None = Field(exclude=True)
    label_fr: str
    label_en: str|None = Field(exclude=True)
    synonyms_fr: list[str]|None
    synonyms_en: list[str]|None = Field(exclude=True)