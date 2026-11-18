"""An organization's invitation settings: after how many days a reminder is due.

The list's resend mode preselects the pending invitations whose last email is
older than this many days, so someone just reached by a batch is not mailed
again by reflex. Administrators send the reminders, so they read it; changing
it is a superuser's decision. 30 days unless the organization says otherwise.
"""
import uuid
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]

URL = "/api/v2/invitation-settings"


@pytest.fixture
def organization(site):
    from facility.models import Organization

    return Organization.objects.create(name="settings-org", site=site, neomodel_uid=uuid.uuid4())


@contextmanager
def as_role(patch_jwt, jwt, role):
    with patch_jwt(jwt), patch(
        "api.routers.invitation_settings.get_neo4j_role", new_callable=AsyncMock, return_value=role,
    ):
        yield


async def test_a_reminder_is_due_after_30_days_by_default(versioned_client, patch_jwt, jwt_administrator, organization):
    with as_role(patch_jwt, jwt_administrator, "administrator"):
        response = await versioned_client.get(URL)

    assert response.status_code == 200, response.text
    assert response.json() == {"resendAfterDays": 30}


async def test_below_administrator_reads_nothing(versioned_client, patch_jwt, jwt_staff, organization):
    with as_role(patch_jwt, jwt_staff, "staff"):
        response = await versioned_client.get(URL)

    assert response.status_code == 403


async def test_an_administrator_may_not_change_it(versioned_client, patch_jwt, jwt_administrator, organization):
    with as_role(patch_jwt, jwt_administrator, "administrator"):
        response = await versioned_client.patch(URL, json={"resendAfterDays": 7})

    assert response.status_code == 403
    await organization.arefresh_from_db()
    assert organization.invitation_resend_after_days == 30


async def test_a_superuser_changes_it(versioned_client, patch_jwt, jwt_superuser, organization):
    with as_role(patch_jwt, jwt_superuser, "superuser"):
        response = await versioned_client.patch(URL, json={"resendAfterDays": 7})

    assert response.status_code == 200, response.text
    assert response.json() == {"resendAfterDays": 7}
    await organization.arefresh_from_db()
    assert organization.invitation_resend_after_days == 7


@pytest.mark.parametrize("days", [0, 366])
async def test_it_stays_between_a_day_and_a_year(versioned_client, patch_jwt, jwt_superuser, organization, days):
    with as_role(patch_jwt, jwt_superuser, "superuser"):
        response = await versioned_client.patch(URL, json={"resendAfterDays": days})

    assert response.status_code == 422
