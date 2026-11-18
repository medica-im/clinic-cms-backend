"""An organisation has a time zone, returned next to its language.

The frontend formats dates (blog post cards, opening hours) with
`Intl.DateTimeFormat`. Without an explicit `timeZone`, SSR formats in the
server's zone (UTC in the container) and hydration in the browser's, so a post
published at 00:30 in Paris shows two different days. Every site served today
is in metropolitan France, hence the default; an overseas site
(America/Martinique, Indian/Reunion...) sets its own.

The value must be an IANA name the browser knows: `Intl` throws a RangeError on
anything else, which would take the whole page down rather than one date.
"""
import uuid

import pytest
from django.core.exceptions import ValidationError

from tests.api.test_organization_payload_is_async import (  # noqa: F401
    make_organization,
    organization_entry,
)


@pytest.mark.django_db
def test_a_new_organization_is_in_paris_by_default():
    from facility.models import Organization

    org = Organization.objects.create(name=f"tz-{uuid.uuid4().hex[:8]}")

    assert org.timezone == "Europe/Paris"


@pytest.mark.django_db
def test_an_unknown_time_zone_is_refused():
    from facility.models import Organization

    org = Organization(name=f"tz-{uuid.uuid4().hex[:8]}", timezone="Europe/Pariss")

    with pytest.raises(ValidationError) as excinfo:
        org.full_clean(exclude=[f.name for f in Organization._meta.fields if f.name != "timezone"])

    assert "timezone" in excinfo.value.message_dict


@pytest.mark.django_db
def test_an_overseas_time_zone_is_accepted():
    from facility.models import Organization

    org = Organization(name=f"tz-{uuid.uuid4().hex[:8]}", timezone="America/Martinique")

    org.full_clean(exclude=[f.name for f in Organization._meta.fields if f.name != "timezone"])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_the_payload_carries_the_time_zone(organization_entry):  # noqa: F811
    from api.serializers.organization import async_get_django_organization
    from api.types.organization import Organization as OrganizationPy

    org = await make_organization(organization_entry)
    payload = await async_get_django_organization(org)

    assert OrganizationPy.model_validate(payload).timezone == "Europe/Paris"
