from pydantic import BaseModel

class WebsitePy(BaseModel):
    url: str


class WebsitePost(BaseModel):
    url: str