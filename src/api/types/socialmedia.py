from typing import FrozenSet, Optional, Set
from enum import Enum
from pydantic import BaseModel
from .shared import Roles, Role

class SocialMediaTypes(str, Enum):
    TWITTER = 'T'
    LINKEDIN = 'LI'
    FACEBOOK = 'F'
    PINTEREST = 'P'
    INSTAGRAM = 'I'
    YOUTUBE = 'YT'
    TIKTOK = 'TT'
    SNAPCHAT = 'SC'
    TWITCH = 'TH'
    BLUESKY = 'B'
    MASTODON = 'M'


class SocialMediaPut(BaseModel):
    url: str
    type: SocialMediaTypes
    roles: list[Roles]


class SocialMedia(BaseModel):
    id: int
    url: str
    type: SocialMediaTypes
    type_display: str
    roles: list[Role]


class SocialMediaPost(BaseModel):
    url: str
    type: SocialMediaTypes
    roles: list[Roles]
    entry: str