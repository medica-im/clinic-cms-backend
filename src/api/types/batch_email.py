from pydantic import BaseModel


class BatchEmailPost(BaseModel):
    recipient_uids: list[str]
    subject: str
    body: str
    author_uid: str


class BatchEmailResponse(BaseModel):
    task_id: str
    message: str


class BatchEmailMessage(BaseModel):
    id: int
    author_uid: str
    subject: str
    sent_at: int
    recipient_uids: list[str]
    mailgun_response: dict
    success: bool


class BatchEmailMessageDetail(BatchEmailMessage):
    body: str
