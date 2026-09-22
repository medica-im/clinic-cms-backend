"""An invitation goes out under the inviting organization's identity.

Both invitation paths -- the single invite from the FastAPI endpoint and the
batch invite run in Celery -- already resolve the Organization from the Site.
These tests pin that they pass it on to the mailer, so the recipient sees the
organization that actually invited them rather than a shared address.

The Celery tasks take an organization id rather than a resolved sender:
a SenderConfig is not JSON-serialisable, and resolving inside the worker also
picks up a credential change made between queueing and sending.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mailer.config import SenderConfig


ORG_SENDER = SenderConfig(
    api_url="https://api.eu.mailgun.net/v3/mail.example.org/messages",
    auth=("org-key-id", "org-key"),
    from_address="Cabinet Example <contact@example.org>",
)


class FakeOrganization:
    id = 42
    neomodel_uid = MagicMock(hex="org-uid")
    formatted_name = "Cabinet Example"

    def __str__(self):
        return self.formatted_name


class FakeSite:
    domain = "annuaire.example.org"


class FakeInvitee:
    email = "who@example.org"
    name = "Who"


@pytest.mark.asyncio
async def test_a_single_invitation_queues_with_the_organization_id():
    from api.serializers.invitee import notification_email

    org = FakeOrganization()
    with (
        patch(
            "api.serializers.invitee.Organization.objects.aget",
            new_callable=AsyncMock,
            return_value=org,
        ),
        patch("api.serializers.invitee.send_single_email_task") as task,
    ):
        await notification_email(FakeInvitee(), FakeSite())

    assert task.delay.call_args.kwargs["organization_id"] == org.id


def test_the_single_email_task_resolves_the_sender_from_the_organization():
    from mailer.tasks import send_single_email_task

    org = FakeOrganization()
    with (
        patch(
            "mailer.tasks.Organization.objects.get", return_value=org
        ) as get_org,
        patch("mailer.tasks.get_sender", return_value=ORG_SENDER),
        patch("mailer.tasks.send_single_email", return_value={}) as send,
    ):
        send_single_email_task("who@example.org", "s", "b", organization_id=org.id)

    get_org.assert_called_once_with(id=org.id)
    assert send.call_args.kwargs["sender"] == ORG_SENDER


def test_the_single_email_task_still_works_without_an_organization():
    """Nothing breaks for a caller that has no organization to name."""
    from mailer.tasks import send_single_email_task

    with (
        patch("mailer.tasks.get_sender", return_value=SenderConfig.default()),
        patch("mailer.tasks.send_single_email", return_value={}) as send,
    ):
        send_single_email_task("who@example.org", "s", "b")

    assert send.call_args.kwargs["sender"] == SenderConfig.default()


def test_a_batch_invitation_sends_under_the_organization_identity():
    from access.tasks import _send_notification_email

    org = FakeOrganization()
    with (
        patch("django.contrib.sites.models.Site.objects.get", return_value=FakeSite()),
        patch("facility.models.Organization.objects.get", return_value=org),
        patch("mailer.config.get_sender", return_value=ORG_SENDER),
        patch("mailer.main.send_single_email", return_value={}) as send,
    ):
        ok = _send_notification_email("who@example.org", "Who", "annuaire.example.org")

    assert ok is True
    assert send.call_args.kwargs["sender"] == ORG_SENDER


@pytest.mark.asyncio
async def test_a_batch_email_queues_with_the_requesting_organization():
    """The newsletter endpoint sends under the organization too.

    A recipient must never see two different From addresses from the same
    organization depending on which feature sent the mail.
    """
    from api.routers.batch_emails import send_batch_emails_endpoint
    from api.types.batch_email import BatchEmailPost

    org = FakeOrganization()
    user = MagicMock(email="who@example.org", name="Who")

    with (
        patch("api.routers.batch_emails.authorize_api", new_callable=AsyncMock),
        patch(
            "api.routers.batch_emails.Neo4jUser.nodes",
            MagicMock(get=AsyncMock(return_value=user)),
        ),
        patch(
            "api.routers.batch_emails.get_site_from_request",
            new_callable=AsyncMock,
            return_value=FakeSite(),
        ),
        patch(
            "api.routers.batch_emails.Organization.objects.aget",
            new_callable=AsyncMock,
            return_value=org,
        ),
        patch(
            "api.routers.batch_emails.send_batch_emails_task",
            MagicMock(delay=MagicMock(return_value=MagicMock(id="task-1"))),
        ) as task,
    ):
        await send_batch_emails_endpoint(
            BatchEmailPost(
                recipient_uids=["u1"],
                author_uid="a1",
                subject="Subject",
                body="Body",
            ),
            MagicMock(),
            {},
        )

    assert task.delay.call_args.kwargs["organization_id"] == org.id
