"""A reminder to many pending invitations is a batch job: a resend.

It runs only the sending step of an import (access.tasks), over invitations
that already exist, so it gets what an import has: emails sent one after the
other, a cancel, a progress, and a report in the batch history.

* An invitation resend_refusal turns down is skipped, with why: used,
  deactivated, or its previous email still on its way.
* A remembered bad address is never forced: one bounce too many hurts the
  sending domain for every organization on it.
* Only one batch at a time per organization: a running import's invitations
  have no email yet, so a reminder started beside it would mail them twice.
"""
import uuid
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from fastapi import HTTPException

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]

ENTRY_UID = uuid.uuid4().hex
OTHER_ENTRY_UID = uuid.uuid4().hex
PENDING, USED, DISABLED, QUEUED = (uuid.uuid4().hex for _ in range(4))
URL = "/api/v2/batch-invitees/resend"


@pytest.fixture
async def graph(neo4j_graph):
    await neo4j_graph.cypher_query(
        """
        CREATE (e:Entry {uid: $entry}), (:Entry {uid: $other})
        CREATE (:Invitee {uid: $pending, email: 'pending@example.com', name: 'Pending', active: true})-[:INVITED_TO]->(e)
        CREATE (:Invitee {uid: $used, email: 'used@example.com', active: true, redeemedAt: 1})-[:INVITED_TO]->(e)
        CREATE (:Invitee {uid: $disabled, email: 'disabled@example.com', active: false})-[:INVITED_TO]->(e)
        CREATE (:Invitee {uid: $queued, email: 'queued@example.com', active: true})-[:INVITED_TO]->(e)
        """,
        {"entry": ENTRY_UID, "other": OTHER_ENTRY_UID, "pending": PENDING,
         "used": USED, "disabled": DISABLED, "queued": QUEUED},
    )
    return neo4j_graph


async def _job(**fields):
    from access.models import BatchInviteeJob

    defaults = dict(
        organization_neomodel_uid=uuid.UUID(ENTRY_UID), user_uid="x", total_rows=4,
        role="", send_emails=True, kind=BatchInviteeJob.Kind.RESEND,
    )
    return await BatchInviteeJob.objects.acreate(**{**defaults, **fields})


# --- The job -------------------------------------------------------------------


@pytest.mark.integration
async def test_only_the_invitations_that_may_be_sent_again_are_sent(graph):
    from access.tasks import process_batch_resend
    from mailer.delivery import record_queued

    await sync_to_async(record_queued)(QUEUED, "queued@example.com")
    job = await _job()
    uids = [PENDING, USED, DISABLED, QUEUED]

    with patch("access.tasks._send_notification_email", return_value=True) as send:
        await sync_to_async(process_batch_resend)(job.id, uids, "testserver")
    await job.arefresh_from_db()

    send.assert_called_once_with(
        "pending@example.com", "Pending", "testserver", invitee_uid=PENDING, batch_job_uid=job.uid,
    )
    skipped = {row["invitee_uid"]: row.get("email_skipped") for row in job.summary}
    assert skipped == {PENDING: None, USED: "used", DISABLED: "disabled", QUEUED: "already_queued"}
    assert (job.status, job.phase) == ("completed", "sending")
    assert (job.emails_processed, job.email_skipped_count, job.failed_email_count) == (4, 3, 0)


@pytest.mark.integration
async def test_the_report_lists_each_invitation_with_its_address(graph):
    from access.tasks import process_batch_resend

    job = await _job(total_rows=1)
    with patch("access.tasks._send_notification_email", return_value=True):
        await sync_to_async(process_batch_resend)(job.id, [PENDING], "testserver")
    await job.arefresh_from_db()

    assert [(row["row"], row["email"], row["name"]) for row in job.summary] == [
        (1, "pending@example.com", "Pending"),
    ]


# --- Starting it ---------------------------------------------------------------


@contextmanager
def authorized(entry_uid=ENTRY_UID, refuse=False):
    guard = AsyncMock(side_effect=HTTPException(403)) if refuse else AsyncMock()
    task = MagicMock()
    task.delay.return_value = MagicMock(id="task-id")
    with patch("api.routers.batch_invitees.authorize_api", guard), \
            patch("api.routers.batch_invitees._get_organization_entry_uid", new_callable=AsyncMock,
                  return_value=(entry_uid, "testserver")), \
            patch("api.routers.batch_invitees.process_batch_resend", task):
        yield task


async def _jobs():
    from access.models import BatchInviteeJob

    return [job async for job in BatchInviteeJob.objects.all()]


@pytest.mark.integration
async def test_a_resend_is_queued_as_a_batch_job(graph, versioned_client, patch_jwt, jwt_administrator):
    with patch_jwt(jwt_administrator), authorized() as task:
        response = await versioned_client.post(URL, json={"uids": [PENDING, USED]})

    assert response.status_code == 201, response.text
    [job] = await _jobs()
    assert str(job.uid) == response.json()["job_uid"]
    assert (job.kind, job.total_rows, job.status) == ("resend", 2, "pending")
    task.delay.assert_called_once_with(job_id=job.id, invitee_uids=[PENDING, USED], site_domain="testserver")


@pytest.mark.integration
async def test_another_organizations_invitation_is_refused(graph, versioned_client, patch_jwt, jwt_administrator):
    with patch_jwt(jwt_administrator), authorized(entry_uid=OTHER_ENTRY_UID) as task:
        response = await versioned_client.post(URL, json={"uids": [PENDING]})

    assert response.status_code == 403
    assert await _jobs() == []
    task.delay.assert_not_called()


async def test_a_caller_without_the_right_starts_nothing(versioned_client, patch_jwt, jwt_staff):
    with patch_jwt(jwt_staff), authorized(refuse=True) as task:
        response = await versioned_client.post(URL, json={"uids": [PENDING]})

    assert response.status_code == 403
    assert await _jobs() == []
    task.delay.assert_not_called()


@pytest.mark.parametrize("running", ["pending", "processing"])
async def test_not_while_a_batch_is_running(versioned_client, patch_jwt, jwt_administrator, running):
    from access.models import BatchInviteeJob

    await _job(kind=BatchInviteeJob.Kind.CREATE, status=running)
    with patch_jwt(jwt_administrator), authorized() as task:
        response = await versioned_client.post(URL, json={"uids": [PENDING]})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "batch_running"
    task.delay.assert_not_called()


async def test_at_most_5000_invitations_at_once(versioned_client, patch_jwt, jwt_administrator):
    uids = [uuid.uuid4().hex for _ in range(5001)]
    with patch_jwt(jwt_administrator), authorized() as task:
        response = await versioned_client.post(URL, json={"uids": uids})

    assert response.status_code == 422
    task.delay.assert_not_called()


# --- Finding it again ------------------------------------------------------------


async def test_the_latest_resend_can_be_asked_for(versioned_client, patch_jwt, jwt_administrator):
    from access.models import BatchInviteeJob

    await _job(status="completed")
    latest = await _job(status="completed")
    await _job(kind=BatchInviteeJob.Kind.CREATE, status="completed", role="staff")

    with patch_jwt(jwt_administrator), authorized():
        response = await versioned_client.get("/api/v2/batch-invitees?kind=resend&limit=1")

    assert response.status_code == 200, response.text
    [job] = response.json()
    assert (job["uid"], job["kind"]) == (str(latest.uid), "resend")
