from pydantic import BaseModel

class Tag(BaseModel):
    uid: str
    label: str
    labelShort: str|None
    name: str
    definition: str|None
    synonyms: list[str]|None
    category: str


class TagCategory(BaseModel):
    uid: str
    label: str
    labelShort: str|None
    name: str
    definition: str|None
    synonyms: list[str]|None
    effector_types: list[str]|None


class TagEntry(BaseModel):
    entry: str
    addTags: list[str]|None
    removeTags: list[str]|None