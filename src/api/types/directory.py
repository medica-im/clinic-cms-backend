from typing import Literal

from pydantic import BaseModel

# The roles of directory.models Directory.minimum_role, least first.
MinimumRole = Literal["anonymous", "staff", "administrator", "superuser"]

class AvailableDirectory(BaseModel):
    name: str
    display_name: str


class DirectoryOwner(BaseModel):
    uid: str
    label: str | None = None


class OfferedEffectorType(BaseModel):
    uid: str
    label: str | None = None


class DirectorySettings(BaseModel):
    """A directory as the "Annuaires" page shows it (Neo4j node)."""
    uid: str
    name: str
    display_name: str | None = None
    owner: DirectoryOwner | None = None
    list_owner_entry: bool = True
    # Empty: every type is offered (directory/offered_types.py).
    effector_types: list[OfferedEffectorType] = []
    # The site's own directory: always public, so it takes no minimum role.
    main: bool = False
    # The least role that may list it when reached as a sibling (?directory=).
    minimum_role: MinimumRole = "anonymous"


class DirectorySettingsUpdate(BaseModel):
    """Only the fields sent are changed."""
    list_owner_entry: bool | None = None
    minimum_role: MinimumRole | None = None


class OfferedEffectorTypePost(BaseModel):
    effector_type: str
