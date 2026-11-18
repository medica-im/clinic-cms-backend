"""How many invitations one spreadsheet may create: per organization.

A flat 500 suited a CPTS of a few hundred professionals but not a national
union like UNIPA, so the limit is now Organization.batch_invitation_max_rows,
and an organization that has not set one gets settings.BATCH_INVITATION_MAX_ROWS
(1000).

The upload page is told the limit and the file's row count when the file is
parsed, so a file that is too long is said to be before anything is sent, not
discovered as a refusal at the last step.
"""
import io
import json
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]

MAPPING = json.dumps({"email_column": "email"})


def csv_with(rows: int) -> bytes:
    lines = ["email"] + [f"person{i}@example.org" for i in range(rows)]
    return ("\n".join(lines) + "\n").encode()


@pytest.fixture
def organization(site):
    from facility.models import Organization
    import uuid
    return Organization.objects.create(name="limit-test-org", site=site, neomodel_uid=uuid.uuid4())


@contextmanager
def authorized(site):
    """Past the gate and the graph: what is under test is the count."""
    task = MagicMock()
    task.delay.return_value = MagicMock(id="task-id")
    with patch("api.routers.batch_invitees.authorize_api", new_callable=AsyncMock), \
            patch("api.routers.batch_invitees.get_site_from_request", new_callable=AsyncMock, return_value=site), \
            patch("api.routers.batch_invitees.adb.cypher_query", new_callable=AsyncMock, return_value=([["user-uid"]], None)), \
            patch("api.routers.batch_invitees.process_batch_invitees", task):
        yield task


async def create(client, rows: int):
    return await client.post(
        "/api/v2/batch-invitees/create",
        files={"file": ("people.csv", io.BytesIO(csv_with(rows)), "text/csv")},
        data={"mapping_json": MAPPING, "role": "staff", "send_emails": "false"},
    )


async def parse(client, rows: int):
    return await client.post(
        "/api/v2/batch-invitees/parse",
        files={"file": ("people.csv", io.BytesIO(csv_with(rows)), "text/csv")},
    )


async def set_limit(organization, value):
    organization.batch_invitation_max_rows = value
    await sync_to_async(organization.save)()


class TestTheLimit:
    async def test_without_its_own_the_default_applies(self, organization):
        from django.conf import settings
        from api.routers.batch_invitees import batch_max_rows

        assert settings.BATCH_INVITATION_MAX_ROWS == 1000
        assert batch_max_rows(organization) == 1000

    async def test_an_organization_may_set_its_own(self, organization):
        from api.routers.batch_invitees import batch_max_rows

        await set_limit(organization, 2500)
        assert batch_max_rows(organization) == 2500


class TestCreating:
    async def test_a_file_at_the_limit_is_accepted(self, versioned_client, patch_jwt, jwt_administrator, site, organization):
        await set_limit(organization, 3)
        with patch_jwt(jwt_administrator), authorized(site) as task:
            r = await create(versioned_client, 3)
        assert r.status_code == 201, r.text
        assert task.delay.called

    async def test_a_file_over_the_limit_is_refused_saying_the_limit(self, versioned_client, patch_jwt, jwt_administrator,
                                                                    site, organization):
        await set_limit(organization, 3)
        with patch_jwt(jwt_administrator), authorized(site) as task:
            r = await create(versioned_client, 4)
        assert r.status_code == 400
        assert "3" in r.json()["detail"]
        assert not task.delay.called

    async def test_the_old_500_no_longer_applies(self, versioned_client, patch_jwt, jwt_administrator, site, organization):
        with patch_jwt(jwt_administrator), authorized(site):
            r = await create(versioned_client, 501)
        assert r.status_code == 201, r.text


class TestParsing:
    async def test_the_page_is_told_the_limit_and_the_count(self, versioned_client, patch_jwt, jwt_administrator,
                                                           site, organization):
        await set_limit(organization, 3)
        with patch_jwt(jwt_administrator), authorized(site):
            r = await parse(versioned_client, 5)
        assert r.status_code == 200, r.text
        assert r.json()["max_rows"] == 3
        assert r.json()["total_rows"] == 5
