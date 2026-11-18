from pydantic import BaseModel, Field

class MonkeyPost(BaseModel):
    name: str


class Monkey(MonkeyPost):
    uid: str
