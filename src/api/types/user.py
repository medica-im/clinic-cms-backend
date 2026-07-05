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


class UserMeOut(BaseModel):
    uid: str
    name: str | None = None
    email: str | None = None
    picture: str | None = None
    role: str | None = None
    gender: str | None = None
    effector: str | None = None
    full_name: str | None = None
