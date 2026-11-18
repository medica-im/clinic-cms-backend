"""A batch import creates every invitation, then sends the emails.

Creating and sending are two steps of one job, not one loop. The sending step
is the one a resend job runs on its own, and a cancel while sending leaves
created, unsent invitations that the list's resend mode can pick up.
"""
import uuid
from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from neomodel import db

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

ENTRY_UID = uuid.uuid4().hex
ROWS = [{"email": f"person{i}@example.com", "name": ""} for i in range(3)]


@pytest.fixture
async def graph(neo4j_graph):
    await neo4j_graph.cypher_query("CREATE (:Entry {uid: $uid})", {"uid": ENTRY_UID})
    return neo4j_graph


async def _job():
    from access.models import BatchInviteeJob

    return await BatchInviteeJob.objects.acreate(
        organization_neomodel_uid=uuid.UUID(ENTRY_UID), user_uid="x",
        total_rows=len(ROWS), role="staff", send_emails=True,
    )


async def _run(job, send_emails=True):
    from access.tasks import process_batch_invitees

    await sync_to_async(process_batch_invitees)(
        job.id, ROWS, ENTRY_UID, "no-such-sub", "staff", send_emails, "testserver",
    )
    await job.arefresh_from_db()


def _invitee_count():
    rows, _ = db.cypher_query("MATCH (i:Invitee) RETURN count(i)")
    return rows[0][0]


async def test_every_invitation_is_created_before_the_first_email(graph):
    created_when_sending = []

    def send(*args, **kwargs):
        created_when_sending.append(_invitee_count())
        return True

    job = await _job()
    with patch("access.tasks._send_notification_email", side_effect=send):
        await _run(job)

    assert created_when_sending == [3, 3, 3]


async def test_the_job_says_how_far_the_sending_got(graph):
    job = await _job()
    with patch("access.tasks._send_notification_email", return_value=True):
        await _run(job)

    assert (job.phase, job.emails_total, job.emails_processed) == ("sending", 3, 3)
    assert job.status == "completed"


async def test_a_cancel_while_sending_leaves_the_rest_unsent(graph):
    from access.models import BatchInviteeJob

    job = await _job()

    def send(*args, **kwargs):
        BatchInviteeJob.objects.filter(id=job.id).update(status=BatchInviteeJob.Status.CANCELLED)
        return True

    with patch("access.tasks._send_notification_email", side_effect=send) as sent:
        await _run(job)

    assert sent.call_count == 1
    assert job.status == "cancelled"
    assert job.emails_processed == 1
    rows, _ = await graph.cypher_query("MATCH (i:Invitee) RETURN count(i)")
    assert rows[0][0] == 3


async def test_a_failed_email_is_flagged_on_its_row(graph):
    job = await _job()
    with patch("access.tasks._send_notification_email", side_effect=[True, False, True]):
        await _run(job)

    assert [bool(row.get("email_error")) for row in job.summary] == [False, True, False]
    assert job.failed_email_count == 1


async def test_without_emails_nothing_is_sent(graph):
    job = await _job()
    with patch("access.tasks._send_notification_email") as sent:
        await _run(job, send_emails=False)

    sent.assert_not_called()
    assert job.phase == "creating"
    assert job.status == "completed"
