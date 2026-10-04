from pydantic import BaseModel

class AvailableDirectory(BaseModel):
    name: str
    display_name: str


class DirectoryOwner(BaseModel):
    uid: str
    label: str | None = None


class DirectorySettings(BaseModel):
    """A directory as the superuser "Annuaires" page shows it (Neo4j node)."""
    uid: str
    name: str
    display_name: str | None = None
    owner: DirectoryOwner | None = None
    list_owner_entry: bool = True


class DirectorySettingsUpdate(BaseModel):
    list_owner_entry: bool
