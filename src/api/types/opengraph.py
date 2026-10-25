from pydantic import BaseModel


class OpenGraphCard(BaseModel):
    title: str
    username: str
    twitter_description: str
    description: str
    image_url: str | None
    image_alt: str | None
