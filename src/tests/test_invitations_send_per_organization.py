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
    formatted_name_short = "Cab. Ex."
    public_base_url = ""

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


# --- The links in an invitation point at the site's real public URL ---------
#
# A site served under a base path (unipa.fr/annuaire) only exists under that
# prefix: nginx strips it before the request reaches the backend, so
# site.domain alone yields https://unipa.fr/signin, a WordPress 404. The
# organization's public_base_url carries the prefix; blank keeps the
# https://{domain} every root site has always used.


@pytest.fixture(autouse=True)
def builtin_template():
    """Every invitation here renders the built-in text, with no database.

    These tests are about links and senders, not about which template row is
    chosen -- that is test_email_templates.py. Patched where each path looks
    it up: the serializer imports get_template at module level, the Celery
    task inside the function.
    """
    from mailer.defaults import INVITATION_FALLBACK

    def lookup(organization, kind):
        return INVITATION_FALLBACK

    with (
        patch("api.serializers.invitee.get_template", lookup),
        patch("mailer.templating.get_template", lookup),
    ):
        yield


async def _single_invitation(org) -> tuple[str, str]:
    """(subject, message) of the single invitation path."""
    from api.serializers.invitee import notification_email

    with (
        patch(
            "api.serializers.invitee.Organization.objects.aget",
            new_callable=AsyncMock,
            return_value=org,
        ),
        patch("api.serializers.invitee.send_single_email_task") as task,
    ):
        await notification_email(FakeInvitee(), FakeSite())
    return task.delay.call_args.args[1], task.delay.call_args.args[2]


async def _batch_invitation(org) -> tuple[str, str]:
    """(subject, message) of the batch invitation path."""
    from access.tasks import _send_notification_email

    with (
        patch("django.contrib.sites.models.Site.objects.get", return_value=FakeSite()),
        patch("facility.models.Organization.objects.get", return_value=org),
        patch("mailer.config.get_sender", return_value=ORG_SENDER),
        patch("mailer.main.send_single_email", return_value={}) as send,
    ):
        _send_notification_email("who@example.org", "Who", FakeSite.domain)
    return send.call_args.args[1], send.call_args.args[2]


async def _single_invitation_message(org) -> str:
    return (await _single_invitation(org))[1]


async def _batch_invitation_message(org) -> str:
    return (await _batch_invitation(org))[1]


BOTH_PATHS = pytest.mark.parametrize(
    "build_message",
    [_single_invitation_message, _batch_invitation_message],
    ids=["single", "batch"],
)


@pytest.mark.asyncio
@BOTH_PATHS
async def test_a_root_site_invitation_links_to_its_domain(build_message):
    message = await build_message(FakeOrganization())

    assert "https://annuaire.example.org/signin" in message
    assert "https://annuaire.example.org/contact" in message


@pytest.mark.asyncio
@BOTH_PATHS
async def test_a_base_path_site_invitation_links_under_its_base_path(build_message):
    org = FakeOrganization()
    org.public_base_url = "https://example.org/annuaire"

    message = await build_message(org)

    assert "https://example.org/annuaire/signin" in message
    assert "https://example.org/annuaire/contact" in message
    assert "annuaire.example.org/signin" not in message


@pytest.mark.asyncio
@BOTH_PATHS
async def test_a_trailing_slash_in_the_base_url_does_not_double(build_message):
    org = FakeOrganization()
    org.public_base_url = "https://example.org/annuaire/"

    message = await build_message(org)

    assert "https://example.org/annuaire/signin" in message
    assert "//signin" not in message


# --- The service is named where it lives, base path included ----------------
#
# "le service dev.unipa.fr" names the WordPress at the root, not the directory
# the invitee is being sent to: the service is dev.unipa.fr/annuaire. It is
# the site URL without its scheme, so a root site keeps its bare domain.

BOTH_PATHS_FULL = pytest.mark.parametrize(
    "build", [_single_invitation, _batch_invitation], ids=["single", "batch"]
)


@pytest.mark.asyncio
@BOTH_PATHS_FULL
async def test_a_base_path_site_is_named_with_its_base_path(build):
    org = FakeOrganization()
    org.public_base_url = "https://example.org/annuaire/"

    subject, message = await build(org)

    assert subject == "Cabinet Example vous invite à utiliser le service example.org/annuaire"
    assert "service en ligne example.org/annuaire." in message
    assert "votre compte sur example.org/annuaire sera créé" in message


@pytest.mark.asyncio
@BOTH_PATHS_FULL
async def test_a_root_site_is_named_by_its_domain(build):
    subject, message = await build(FakeOrganization())

    assert subject == "Cabinet Example vous invite à utiliser le service annuaire.example.org"
    assert "service en ligne annuaire.example.org." in message
    assert "votre compte sur annuaire.example.org sera créé" in message
