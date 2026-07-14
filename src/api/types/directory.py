from pydantic import BaseModel

class AvailableDirectory(BaseModel):
    name: str
    display_name: str
