from pydantic import BaseModel, Field

class AdministrativeTerritorialEntityOfFrance(BaseModel):
    uid: str
    name_en: str|None = Field(exclude=True)
    name_fr: str
    slug_en: str|None = Field(exclude=True)
    slug_fr: str
    wikidata: str|None

class DepartmentOfFrance(BaseModel):
    uid: str
    name: str
    code: str
    slug: str
    wikidata: str

class Commune(AdministrativeTerritorialEntityOfFrance):
    department: DepartmentOfFrance


