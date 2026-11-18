"""An organization's own wording of the emails it sends.

A thin shell over mailer.editing: authorise, resolve the site's organization,
and turn TemplateInvalid into a 422 whose problems are codes the frontend
translates. Gated by api.email_access: administrators and higher read and
preview; the role the organization chose changes.
"""

import logging
from dataclasses import asdict
from typing import Annotated

from asgiref.sync import sync_to_async
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from api.auth import JWT
from api.email_access import EmailAccess, email_access
from api.types.email_template import (
    EmailTemplateDraft,
    EmailTemplateOut,
    EmailTemplatePreview,
    EmailTemplatePreviewRequest,
)
from mailer.editing import (
    TemplateInvalid,
    effective_template,
    placeholder_values,
    preview_template,
    reset_template,
    save_template,
)
from mailer.access import editor_role
from mailer.models import EmailTemplate
from mailer.templating import PLACEHOLDERS, REQUIRED_IN_BODY

logger = logging.getLogger(__name__)

router = APIRouter()

async def _access(kind: str, request: Request, jwt: dict, *, edit: bool = False) -> EmailAccess:
    access = await email_access(request, jwt, edit=edit)
    if kind not in EmailTemplate.Kind.values:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Unknown email kind: {kind}")
    return access


def _unprocessable(error: TemplateInvalid) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"problems": [asdict(p) for p in error.problems]},
    )


def _out(kind: str, template, source: str, access: EmailAccess) -> EmailTemplateOut:
    required = REQUIRED_IN_BODY.get(kind)
    return EmailTemplateOut(
        kind=kind,
        source=source,
        subject=template.subject,
        body=template.body,
        body_text=template.body_text,
        content_type=template.content_type,
        placeholders=list(PLACEHOLDERS[kind]),
        required_placeholders=[required] if required else [],
        placeholder_values=placeholder_values(access.organization, access.site.domain, kind),
        can_edit=access.can_edit,
        editor_role=editor_role(access.organization),
        updated=getattr(template, "updated", None),
    )


@router.get("/email-templates/{kind}", response_model=EmailTemplateOut)
async def get_email_template(kind: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    access = await _access(kind, request, jwt)
    template, source = await sync_to_async(effective_template)(access.organization, kind)
    return _out(kind, template, source, access)


@router.put("/email-templates/{kind}", response_model=EmailTemplateOut)
async def put_email_template(
    kind: str,
    draft: EmailTemplateDraft,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    access = await _access(kind, request, jwt, edit=True)
    try:
        row = await sync_to_async(save_template)(access.organization, kind, **draft.model_dump())
    except TemplateInvalid as error:
        raise _unprocessable(error)
    return _out(kind, row, "organization", access)


@router.delete("/email-templates/{kind}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_email_template(kind: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    access = await _access(kind, request, jwt, edit=True)
    await sync_to_async(reset_template)(access.organization, kind)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/email-templates/{kind}/preview", response_model=EmailTemplatePreview)
async def preview_email_template(
    kind: str,
    draft: EmailTemplatePreviewRequest,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    access = await _access(kind, request, jwt)
    try:
        email, problems = await sync_to_async(preview_template)(
            access.organization, access.site.domain, kind, **draft.model_dump()
        )
    except TemplateInvalid as error:
        raise _unprocessable(error)
    return EmailTemplatePreview(
        subject=email.subject,
        text=email.text,
        html=email.html,
        problems=[asdict(p) for p in problems],
    )
