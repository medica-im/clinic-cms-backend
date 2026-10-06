from datetime import datetime
from pydantic import BaseModel


class BatchInviteeParseResponse(BaseModel):
    columns: list[str]
    preview_rows: list[dict]
    # Rows in the file, and the most this organization may send at once:
    # the page says a file is too long before it is sent.
    total_rows: int
    max_rows: int


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
    # Each row may carry "email_delivery": where its email stands now
    # (api.types.invitee.EmailDelivery), read from the delivery records.
    summary: list[dict]
    created_at: datetime
    role: str
    send_emails: bool
    # Emails of this batch by current status, and failures by ErrorKind.
    email_status_counts: dict[str, int] = {}
    email_error_kind_counts: dict[str, int] = {}
    # Rows whose address is not sent to automatically (each row's addressIssue).
    address_issue_count: int = 0


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
