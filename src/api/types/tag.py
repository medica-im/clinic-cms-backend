from pydantic import BaseModel

class Tag(BaseModel):
    uid: str
    label: str
    labelShort: str|None
    name: str
    definition: str|None
    synonyms: list[str]|None
    tag_category: str


class TagCategory(BaseModel):
    uid: str
    label: str
    labelShort: str|None
    name: str
    definition: str|None
    synonyms: list[str]|None
    effector_type: list[str]|None