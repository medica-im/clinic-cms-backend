"""How each invitation email was handled, and why it failed, in the report.

A batch report used to say, per row, only "email error" -- a warning triangle
with nothing behind it -- frozen when the job ran. What an administrator needs
is what happened to each email and what to do about it: an address the
service refuses is fixed in the spreadsheet; a misconfigured account is ours
to fix and fails every row; a service that was down is sent again later.

So each EmailDelivery keeps the provider-neutral ErrorKind of its failure, and
belongs to the batch job that sent it. The job report reads those rows when it
is asked -- not a copy taken at the time -- so a status that changes later
(delivered, bounced: the provider's events, to come) shows up in the report
of a job that finished long ago.
"""
import uuid
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest
from asgiref.sync import sync_to_async

from mailer.delivery import batch_report, mark_result, record_queued
from mailer.models import EmailDelivery

UID_A, UID_B, UID_C = "a" * 32, "b" * 32, "c" * 32
ACCEPTED = {"id": "<m@mail.medica.im>", "message": "Queued. Thank you."}
REFUSED = {"error": "'to' parameter is not a valid address", "status_code": 400, "error_kind": "invalid_request"}
DOWN = {"error": "status 503", "status_code": 503, "error_kind": "provider_unavailable"}


class TestTheRecord:
    def test_the_lifecycle_has_its_statuses(self):
        assert set(EmailDelivery.Status.values) == {
            "queued", "sent", "delivered", "deferred", "bounced", "complained", "suppressed", "failed",
        }
        longest = max(len(v) for v in EmailDelivery.Status.values)
        assert EmailDelivery._meta.get_field("status").max_length >= longest

    @pytest.mark.django_db
    def test_a_refusal_keeps_its_kind(self):
        row = record_queued(UID_A, "who@example.org")
        mark_result(row.id, REFUSED)
        row.refresh_from_db()
        assert (row.status, row.error_kind) == ("failed", "invalid_request")

    @pytest.mark.django_db
    def test_an_acceptance_has_no_kind(self):
        row = record_queued(UID_A, "who@example.org")
        mark_result(row.id, ACCEPTED)
        row.refresh_from_db()
        assert (row.status, row.error_kind) == ("sent", "")

    @pytest.mark.django_db
    def test_an_email_belongs_to_the_batch_that_sent_it(self):
        job = uuid.uuid4()
        row = record_queued(UID_A, "who@example.org", batch_job_uid=job)
        assert row.batch_job_uid == job


@pytest.mark.django_db
class TestTheBatchReport:
    def test_counts_by_status_and_by_kind(self):
        job = uuid.uuid4()
        for uid, address, result in ((UID_A, "a@x.org", ACCEPTED), (UID_B, "b@x.org", REFUSED), (UID_C, "c@x.org", DOWN)):
            mark_result(record_queued(uid, address, batch_job_uid=job).id, result)

        report = batch_report(job)

        assert report.status_counts == {"sent": 1, "failed": 2}
        assert report.error_kind_counts == {"invalid_request": 1, "provider_unavailable": 1}
        assert report.by_invitee[UID_B].error_kind == "invalid_request"

    def test_a_resend_replaces_the_rows_status(self):
        """The report says where each invitation stands now, not its first try."""
        job = uuid.uuid4()
        mark_result(record_queued(UID_A, "a@x.org", batch_job_uid=job).id, DOWN)
        mark_result(record_queued(UID_A, "a@x.org").id, ACCEPTED)  # resent from the invitee page

        report = batch_report(job)

        assert report.by_invitee[UID_A].status == "sent"
        assert report.status_counts == {"sent": 1}

    def test_another_jobs_emails_are_not_counted(self):
        mark_result(record_queued(UID_A, "a@x.org", batch_job_uid=uuid.uuid4()).id, ACCEPTED)
        assert batch_report(uuid.uuid4()).status_counts == {}


# --- What the API says ---------------------------------------------------------

@contextmanager
def authorized(entry_uid):
    with patch("api.routers.batch_invitees.authorize_api", new_callable=AsyncMock), \
            patch("api.routers.batch_invitees._get_organization_entry_uid", new_callable=AsyncMock,
                  return_value=(entry_uid, "testserver")):
        yield


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_the_job_detail_says_how_each_email_went(versioned_client, patch_jwt, jwt_administrator):
    from access.models import BatchInviteeJob

    entry_uid = uuid.uuid4().hex
    job = await BatchInviteeJob.objects.acreate(
        organization_neomodel_uid=entry_uid, user_uid="u", total_rows=3, processed_rows=3,
        role="staff", send_emails=True, status=BatchInviteeJob.Status.COMPLETED,
        summary=[
            {"row": 1, "email": "a@x.org", "status": "created", "invitee_uid": UID_A},
            {"row": 2, "email": "b@x.org", "status": "created", "invitee_uid": UID_B},
            {"row": 3, "email": "bad", "status": "failed", "invitee_uid": None},
        ],
    )

    @sync_to_async
    def send():
        mark_result(record_queued(UID_A, "a@x.org", batch_job_uid=job.uid).id, ACCEPTED)
        mark_result(record_queued(UID_B, "b@x.org", batch_job_uid=job.uid).id, REFUSED)

    await send()
    with patch_jwt(jwt_administrator), authorized(entry_uid):
        r = await versioned_client.get(f"/api/v2/batch-invitees/{job.uid}")

    assert r.status_code == 200, r.text
    body = r.json()
    rows = {row["row"]: row for row in body["summary"]}
    assert rows[1]["email_delivery"]["status"] == "sent"
    assert rows[2]["email_delivery"] == {
        "status": "failed", "errorKind": "invalid_request",
        "error": "400: 'to' parameter is not a valid address", "at": rows[2]["email_delivery"]["at"],
        "timedOut": False,
    }
    assert rows[3].get("email_delivery") is None
    assert body["email_status_counts"] == {"sent": 1, "failed": 1}
    assert body["email_error_kind_counts"] == {"invalid_request": 1}


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_an_invitations_delivery_says_why_it_failed():
    from api.routers.invitees import with_email_delivery
    from api.types.invitee import Invitee

    await sync_to_async(lambda: mark_result(record_queued(UID_A, "a@x.org").id, DOWN))()
    [invitee] = await with_email_delivery([Invitee(uid=UID_A, role="staff")])
    assert invitee.emailDelivery.errorKind == "provider_unavailable"
