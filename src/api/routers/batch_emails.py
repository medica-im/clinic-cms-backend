import logging
from typing import Annotated
from fastapi import APIRouter, status, HTTPException, Depends, Request
from access.asyncneomodels import User as Neo4jUser
from api.types.batch_email import BatchEmailPost, BatchEmailResponse, BatchEmailMessage, BatchEmailMessageDetail
from api.auth import JWT, authorize_api
from mailer.tasks import send_batch_emails_task

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/batch-emails", response_model=BatchEmailResponse)
async def send_batch_emails_endpoint(
    item: BatchEmailPost,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    await authorize_api("batch-emails", request, jwt)

    # Look up each recipient User node in Neo4j to get email + name
    recipients = {}
    valid_uids = []
    for uid in item.recipient_uids:
        try:
            user = await Neo4jUser.nodes.get(uid=uid)
        except Neo4jUser.DoesNotExist:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with uid {uid} not found",
            )
        if not user.email:
            logger.warning(f"User {uid} has no email address, skipping")
            continue
        recipients[user.email] = {"name": user.name or "", "uid": uid}
        valid_uids.append(uid)

    if not recipients:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid recipient email addresses found",
        )
    logger.debug(f"{recipients=}")
    # Verify author exists
    try:
        await Neo4jUser.nodes.get(uid=item.author_uid)
    except Neo4jUser.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Author with uid {item.author_uid} not found",
        )

    # Dispatch Celery task (returns immediately)
    task = send_batch_emails_task.delay(
        recipients=recipients,
        subject=item.subject,
        message=item.body,
        author_uid=item.author_uid,
        recipient_uids=valid_uids,
    )

    return BatchEmailResponse(
        task_id=task.id,
        message=f"Batch email queued for {len(recipients)} recipients",
    )


@router.get("/batch-emails", response_model=list[BatchEmailMessage])
async def get_batch_emails(
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    await authorize_api("batch-emails", request, jwt)
    from mailer.models import BatchEmailMessage as BatchEmailMessageModel
    messages = []
    async for m in BatchEmailMessageModel.objects.values(
        "id", "author_uid", "subject", "sent_at",
        "recipient_uids", "mailgun_response", "success",
    ):
        m["author_uid"] = m["author_uid"].hex
        messages.append(BatchEmailMessage(**m))
    return messages


@router.get("/batch-emails/{message_id}", response_model=BatchEmailMessageDetail)
async def get_batch_email(
    message_id: int,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    await authorize_api("batch-emails", request, jwt)
    from mailer.models import BatchEmailMessage as BatchEmailMessageModel
    try:
        obj = await BatchEmailMessageModel.objects.aget(id=message_id)
    except BatchEmailMessageModel.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"BatchEmailMessage with id {message_id} not found",
        )
    return BatchEmailMessageDetail(
        id=obj.id,
        author_uid=obj.author_uid.hex,
        subject=obj.subject,
        body=obj.body,
        sent_at=obj.sent_at,
        recipient_uids=obj.recipient_uids,
        mailgun_response=obj.mailgun_response,
        success=obj.success,
    )
