from pydantic import BaseModel, Field

class ThirdPartyPayer(BaseModel):
    uid: str
    name: str
    label_fr: str
    label_en: str
    definition_fr: str|None
    definition_en: str|None

