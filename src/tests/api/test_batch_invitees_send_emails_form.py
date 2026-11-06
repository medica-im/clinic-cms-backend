"""POST /batch-invitees/create: whether the invitations are mailed.

send_emails is a boolean form field defaulting to True. The upload page always
sends it, as "true" or "false", but how FastAPI reads an *omitted* boolean form
field changed back and forth between 0.147 (omitted meant False, like an
unchecked checkbox) and 0.162 (the declared default again). An import whose
field went missing must still mail its invitations, not silently create them
unannounced.
"""
import io
import json
import uuid
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]

CSV = b"email\nperson@example.org\n"


@pytest.fixture
def organization(site):
    from facility.models import Organization
    return Organization.objects.create(name="send-emails-org", site=site, neomodel_uid=uuid.uuid4())


@contextmanager
def authorized(site):
    """Past the gate and the graph: what is under test is the form field."""
    task = MagicMock()
    task.delay.return_value = MagicMock(id="task-id")
    with patch("api.routers.batch_invitees.authorize_api", new_callable=AsyncMock), \
            patch("api.routers.batch_invitees.get_site_from_request", new_callable=AsyncMock, return_value=site), \
            patch("api.routers.batch_invitees.adb.cypher_query", new_callable=AsyncMock, return_value=([["user-uid"]], None)), \
            patch("api.routers.batch_invitees.process_batch_invitees", task):
        yield task


async def create(client, **fields):
    return await client.post(
        "/api/v2/batch-invitees/create",
        files={"file": ("people.csv", io.BytesIO(CSV), "text/csv")},
        data={"mapping_json": json.dumps({"email_column": "email"}), "role": "staff", **fields},
    )


@pytest.mark.parametrize("fields, mailed", [
    ({"send_emails": "true"}, True),
    ({"send_emails": "false"}, False),
    ({}, True),
], ids=["true", "false", "omitted"])
async def test_send_emails(versioned_client, patch_jwt, jwt_administrator, site, organization, fields, mailed):
    from access.models import BatchInviteeJob

    with patch_jwt(jwt_administrator), authorized(site) as task:
        r = await create(versioned_client, **fields)
    assert r.status_code == 201, r.text
    assert task.delay.call_args.kwargs["send_emails"] is mailed
    job = await BatchInviteeJob.objects.aget(uid=r.json()["job_uid"])
    assert job.send_emails is mailed
