from datetime import datetime
from pydantic import BaseModel


class BatchInviteeParseResponse(BaseModel):
    columns: list[str]
    preview_rows: list[dict]


class BatchInviteeMapping(BaseModel):
    email_column: str
    name_column: str | None = None
    first_name_column: str | None = None
    last_name_column: str | None = None


class BatchInviteeCreateResponse(BaseModel):
    job_uid: str
    status: str


class BatchInviteeProgress(BaseModel):
    uid: str
    status: str
    total_rows: int
    processed_rows: int
    successful_count: int
    failed_count: int
    skipped_duplicate_email_count: int
    skipped_active_user_count: int
    failed_email_count: int
    percentage: float


class BatchInviteeJobDetail(BaseModel):
    uid: str
    status: str
    total_rows: int
    processed_rows: int
    successful_count: int
    failed_count: int
    skipped_duplicate_email_count: int
    skipped_active_user_count: int
    failed_email_count: int
    percentage: float
    summary: list[dict]
    created_at: datetime
    role: str
    send_emails: bool


class BatchInviteeJobListItem(BaseModel):
    uid: str
    created_at: datetime
    status: str
    total_rows: int
    successful_count: int
    failed_count: int
    skipped_duplicate_email_count: int
    skipped_active_user_count: int
    failed_email_count: int
    role: str
