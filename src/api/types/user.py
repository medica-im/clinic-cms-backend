from pydantic import BaseModel


class AccountOut(BaseModel):
    uid: str
    iss: str | None = None
    sub: str
    createdAt: int | None = None


class AccessOut(BaseModel):
    uid: str
    role: str
    createdAt: int | None = None
    active: bool | None = True


class User(BaseModel):
    uid: str
    email: str | None = None
    name: str | None = None
    createdAt: int | None = None
    accounts: list[AccountOut] = []
    access: list[AccessOut] = []
