from pydantic import BaseModel

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


class DirectorySettingsUpdate(BaseModel):
    list_owner_entry: bool


class OfferedEffectorTypePost(BaseModel):
    effector_type: str
