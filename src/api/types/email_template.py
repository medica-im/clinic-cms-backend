from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class EmailTemplateDraft(BaseModel):
    subject: str = Field(max_length=998)
    body: str
    body_text: str = ""
    content_type: Literal["html", "text"] = "html"


class EmailTemplatePreviewRequest(EmailTemplateDraft):
    # None: the made-up invitee of mailer.editing.
    invitee_name: str | None = None
    invitee_email: str | None = None


class EmailTemplateOut(EmailTemplateDraft):
    kind: str
    # organization: its own; default: shared by every organization without
    # its own; builtin: the text in the code, when no row is usable.
    source: Literal["organization", "default", "builtin"]
    placeholders: list[str]
    required_placeholders: list[str]
    # What each placeholder prints on this site; the invitee's own fields hold
    # the made-up invitee of the preview.
    placeholder_values: dict[str, str] = {}
    # Whether the caller may change it, and which role may (the
    # organization's choice): a viewer who may not is shown a read-only page.
    can_edit: bool = False
    editor_role: Literal["administrator", "superuser"] = "superuser"
    updated: datetime | None = None


class TemplateProblemOut(BaseModel):
    field: str
    code: str
    names: list[str] | None = None
    detail: str = ""


class EmailTemplatePreview(BaseModel):
    subject: str
    text: str
    html: str | None
    problems: list[TemplateProblemOut]


class EmailImageOut(BaseModel):
    uid: UUID
    name: str
    alt: str
    width: int
    height: int
    size: int
    created: datetime | None
    # path: for this site's pages; url and thumbnail_url: absolute, for emails.
    path: str
    url: str
    thumbnail_url: str


class EmailImagePatch(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    alt: str | None = Field(default=None, max_length=255)
