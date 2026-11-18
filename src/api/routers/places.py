from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from directory.places import search_places

router = APIRouter()


class Place(BaseModel):
    uid: str
    name: str | None = None
    kind: Literal["country", "region", "department", "commune"]
    code: str | None = None
    department: str | None = None


@router.get("/places")
async def places(q: str = "") -> list[Place]:
    return await search_places(q)
