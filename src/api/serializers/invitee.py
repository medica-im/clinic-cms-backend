import logging
from asgiref.sync import sync_to_async
from api.types.invitee import Invitee
from facility.models import Organization
from mailer.delivery import mark_result, record_queued
from mailer.tasks import send_single_email_task
from mailer.templating import get_template, invitation_context, render_email
from django.contrib.sites.models import Site
from fastapi import status, HTTPException

logger = logging.getLogger(__name__)

async def notification_email(invitee: Invitee, site: Site):
    if not invitee.email:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No email"
        )
    try:
        organization = await Organization.objects.aget(site=site)
    except Organization.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found for this site"
        )

    if not organization.neomodel_uid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization does not have a neomodel_uid"
        )
    template = await sync_to_async(get_template)(organization, "invitation")
    context = invitation_context(organization, site.domain, invitee.name, invitee.email)
    email = render_email(template, context)
    logger.debug(f"{invitee.email=} {email.subject=} {email.text=}")
    # Recorded before it is handed on, so an email that never goes out
    # leaves a trace an administrator can see (mailer.delivery).
    delivery = await sync_to_async(record_queued)(invitee.uid, invitee.email)
    try:
        send_single_email_task.delay(
            invitee.email,
            email.subject,
            email.text,
            organization_id=organization.id,
            html=email.html,
            delivery_id=delivery.id,
        )
    except Exception as error:
        # The invitation exists either way; say that its email did not leave.
        logger.exception(f"Could not queue the invitation email to {invitee.email}")
        await sync_to_async(mark_result)(delivery.id, {"error": f"Could not queue the email: {error}"})
