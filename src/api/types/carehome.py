from pydantic import BaseModel


class CareHome(BaseModel):
    uid: str
    regular_permanent_bed: int | None = None
    regular_temporary_bed: int | None = None
    alzheimer_permanent_bed: int | None = None
    alzheimer_temporary_bed: int | None = None
    uvpha_permanent_bed: int | None = None
    uhr_permanent_bed: int | None = None
    day_care: int | None = None
    usld_permanent_bed: int | None = None
