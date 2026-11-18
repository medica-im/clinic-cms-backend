from typing import Literal

from pydantic import BaseModel


class Concern(BaseModel):
    """A condition or situation a directory offers, with the entries picking it selects."""
    uid: str
    slug: str | None = None
    name: str
    kind: Literal["chapter", "condition", "situation"]
    #: The uid of the node above it in the tree, if any.
    parent: str | None = None
    #: Other names the selector's search matches; never shown as the name.
    synonyms: list[str] = []
    #: The uids of the entries it selects: its own and its descendants'.
    entries: list[str]
    #: The uids of offered situations it can lead to ("voir aussi").
    see_also: list[str] = []
