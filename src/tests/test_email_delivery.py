"""Whether an invitation's email went out, recorded where an administrator can see it.

An invitation that never reached its invitee used to leave no trace: the
worker failed, the invitation was listed as created, and nobody knew until
the invitee said nothing came. Each invitation email is now an EmailDelivery
row -- queued when it is handed to the worker, then sent (Mailgun accepted
it) or failed (with the reason).

A worker that cannot even run the task -- a stale one rejecting a new
argument, a crash before the result is written -- leaves the row queued
forever. Only time reveals it, so a row still queued after QUEUED_TOO_LONG
is shown as failed (timed out) rather than as a wait that will never end:
for the administrator it is the same thing -- the invitee has nothing, and
the answer is to send it again.

"sent" means Mailgun accepted the message, not that it reached the inbox:
that would need Mailgun's delivery webhooks.
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.utils import timezone

from mailer.delivery import (
    QUEUED_TOO_LONG,
    delivery_status,
    latest_deliveries,
    mark_result,
    record_queued,
)
from mailer.models import EmailDelivery
from tests.test_invitations_send_per_organization import builtin_template  # noqa: F401 -- a fixture

UID = "a" * 32
MAILGUN_OK = {"id": "<20260928104645.3e83@mail.medica.im>", "message": "Queued. Thank you."}
MAILGUN_REFUSED = {"error": "Forbidden: domain is not allowed", "status_code": 401}


# --- The record -----------------------------------------------------------------


@pytest.mark.django_db
def test_an_email_handed_to_the_worker_is_queued():
    row = record_queued(UID, "who@example.org")

    assert (row.status, row.invitee_uid, row.to_address) == ("queued", UID, "who@example.org")


@pytest.mark.django_db
def test_an_email_mailgun_accepted_is_sent_with_its_message_id():
    row = record_queued(UID, "who@example.org")

    mark_result(row.id, MAILGUN_OK)

    row.refresh_from_db()
    assert row.status == "sent"
    assert row.provider_message_id == MAILGUN_OK["id"]
    assert row.error == ""


@pytest.mark.django_db
def test_an_email_mailgun_refused_is_failed_with_the_reason():
    row = record_queued(UID, "who@example.org")

    mark_result(row.id, MAILGUN_REFUSED)

    row.refresh_from_db()
    assert row.status == "failed"
    assert "domain is not allowed" in row.error


@pytest.mark.django_db
def test_an_empty_answer_is_a_failure():
    row = record_queued(UID, "who@example.org")

    mark_result(row.id, None)

    row.refresh_from_db()
    assert row.status == "failed"


@pytest.mark.django_db
def test_a_very_long_error_is_kept_short():
    row = record_queued(UID, "who@example.org")

    mark_result(row.id, {"error": "x" * 10_000})

    row.refresh_from_db()
    assert len(row.error) <= 1000


def test_marking_an_unknown_row_is_harmless(db):
    mark_result(999_999, MAILGUN_OK)


# --- What is shown ---------------------------------------------------------------


def _row(status, age=timedelta(0)):
    return SimpleNamespace(status=status, updated=timezone.now() - age, error="")


def test_a_recent_queued_email_is_waiting():
    assert delivery_status(_row("queued")) == "queued"


def test_a_queued_email_nobody_confirmed_has_failed():
    assert delivery_status(_row("queued", QUEUED_TOO_LONG + timedelta(minutes=1))) == "failed"


def test_it_is_told_apart_from_a_refusal_by_having_timed_out():
    from mailer.delivery import timed_out

    assert timed_out(_row("queued", QUEUED_TOO_LONG + timedelta(minutes=1)))
    assert not timed_out(_row("queued"))
    assert not timed_out(_row("failed", timedelta(days=1)))


@pytest.mark.parametrize("status", ["sent", "failed"])
def test_a_settled_email_keeps_its_status_however_old(status):
    assert delivery_status(_row(status, timedelta(days=30))) == status


@pytest.mark.django_db
def test_the_latest_attempt_per_invitation_is_what_counts():
    first = record_queued(UID, "who@example.org")
    mark_result(first.id, MAILGUN_REFUSED)
    second = record_queued(UID, "who@example.org")
    mark_result(second.id, MAILGUN_OK)
    other = record_queued("b" * 32, "other@example.org")

    latest = latest_deliveries([UID, "c" * 32])

    assert latest[UID].id == second.id
    assert "c" * 32 not in latest
    assert other.invitee_uid not in latest


@pytest.mark.django_db
def test_no_invitation_asked_for_means_no_query_result():
    assert latest_deliveries([]) == {}


# --- The worker writes the outcome -------------------------------------------------


def test_the_single_email_task_records_what_mailgun_answered():
    from mailer.tasks import send_single_email_task

    with (
        patch("mailer.tasks.get_sender"),
        patch("mailer.tasks.send_single_email", return_value=MAILGUN_OK),
        patch("mailer.tasks.mark_result") as mark,
    ):
        send_single_email_task("who@example.org", "S", "t", delivery_id=7)

    mark.assert_called_once_with(7, MAILGUN_OK)


def test_the_task_without_a_delivery_records_nothing():
    from mailer.tasks import send_single_email_task

    with (
        patch("mailer.tasks.get_sender"),
        patch("mailer.tasks.send_single_email", return_value=MAILGUN_OK),
        patch("mailer.tasks.mark_result") as mark,
    ):
        send_single_email_task("who@example.org", "S", "t")

    mark.assert_not_called()


# --- The single invitation queues a recorded email ---------------------------------


def _fake_organization():
    from tests.test_invitations_send_per_organization import FakeOrganization

    return FakeOrganization()


@pytest.mark.asyncio
@pytest.mark.usefixtures("builtin_template")
async def test_a_single_invitation_records_its_email_as_queued():
    from api.serializers.invitee import notification_email
    from tests.test_invitations_send_per_organization import FakeSite

    invitee = SimpleNamespace(uid=UID, email="who@example.org", name="Who")
    with (
        patch("api.serializers.invitee.Organization.objects.aget", AsyncMock(return_value=_fake_organization())),
        patch("api.serializers.invitee.record_queued", return_value=SimpleNamespace(id=42)) as record,
        patch("api.serializers.invitee.send_single_email_task") as task,
    ):
        await notification_email(invitee, FakeSite())

    record.assert_called_once_with(UID, "who@example.org")
    assert task.delay.call_args.kwargs["delivery_id"] == 42


@pytest.mark.asyncio
@pytest.mark.usefixtures("builtin_template")
async def test_an_email_the_queue_refused_is_failed_and_the_invitation_stands():
    from api.serializers.invitee import notification_email
    from tests.test_invitations_send_per_organization import FakeSite

    invitee = SimpleNamespace(uid=UID, email="who@example.org", name="Who")
    task = MagicMock()
    task.delay.side_effect = ConnectionError("broker down")
    with (
        patch("api.serializers.invitee.Organization.objects.aget", AsyncMock(return_value=_fake_organization())),
        patch("api.serializers.invitee.record_queued", return_value=SimpleNamespace(id=42)),
        patch("api.serializers.invitee.mark_result") as mark,
        patch("api.serializers.invitee.send_single_email_task", task),
    ):
        await notification_email(invitee, FakeSite())  # does not raise

    assert mark.call_args.args[0] == 42
    assert "broker down" in mark.call_args.args[1]["error"]


# --- The batch invitation records it too, and counts a refusal as a failure --------


def _batch(send_result):
    from access.tasks import _send_notification_email
    from tests.test_invitations_send_per_organization import FakeSite

    with (
        patch("django.contrib.sites.models.Site.objects.get", return_value=FakeSite()),
        patch("facility.models.Organization.objects.get", return_value=_fake_organization()),
        patch("mailer.config.get_sender"),
        patch("mailer.main.send_single_email", return_value=send_result),
        patch("mailer.delivery.record_queued", return_value=SimpleNamespace(id=5)) as record,
        patch("mailer.delivery.mark_result") as mark,
    ):
        ok = _send_notification_email("who@example.org", "Who", FakeSite.domain, invitee_uid=UID)
    return ok, record, mark


@pytest.mark.usefixtures("builtin_template")
def test_a_batch_invitation_email_is_recorded():
    ok, record, mark = _batch(MAILGUN_OK)

    assert ok is True
    record.assert_called_once_with(UID, "who@example.org")
    mark.assert_called_once_with(5, MAILGUN_OK)


@pytest.mark.usefixtures("builtin_template")
def test_a_batch_invitation_mailgun_refused_counts_as_a_failure():
    # send_single_email does not raise: it answers {"error": ...}. The batch
    # used to count that as sent.
    ok, _, mark = _batch(MAILGUN_REFUSED)

    assert ok is False
    mark.assert_called_once_with(5, MAILGUN_REFUSED)


# --- Sending again -----------------------------------------------------------------
#
# An administrator may send an invitation's email again -- after a failure,
# or because the invitee lost it. Not for an invitation that can no longer be
# used, and not while the previous email is still on its way: a double click
# must not send two.


def _invitee(redeemedAt=None, active=True):
    return SimpleNamespace(redeemedAt=redeemedAt, active=active)


def test_an_invitation_may_be_sent_again_after_a_failure():
    from mailer.delivery import resend_refusal

    assert resend_refusal(_invitee(), _row("failed")) is None


def test_an_invitation_may_be_sent_again_when_it_was_sent():
    from mailer.delivery import resend_refusal

    assert resend_refusal(_invitee(), _row("sent")) is None


def test_an_invitation_never_recorded_may_be_sent_again():
    from mailer.delivery import resend_refusal

    assert resend_refusal(_invitee(), None) is None


def test_a_used_invitation_is_not_sent_again():
    from mailer.delivery import resend_refusal

    assert resend_refusal(_invitee(redeemedAt=1790000000000), None) == "used"


def test_a_deactivated_invitation_is_not_sent_again():
    from mailer.delivery import resend_refusal

    assert resend_refusal(_invitee(active=False), None) == "disabled"


def test_an_email_still_on_its_way_is_not_sent_twice():
    from mailer.delivery import resend_refusal

    assert resend_refusal(_invitee(), _row("queued")) == "already_queued"


def test_an_email_queued_too_long_may_be_sent_again():
    from mailer.delivery import resend_refusal

    stale = _row("queued", QUEUED_TOO_LONG + timedelta(minutes=1))

    assert resend_refusal(_invitee(), stale) is None
