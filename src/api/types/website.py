from pydantic import BaseModel
from .shared import Roles

class WebsitePy(BaseModel):
    url: str


class Website(BaseModel):
    id: int
    url: str
    roles: list[Roles]


class WebsitePost(BaseModel):
    url: str
    roles: list[Roles]