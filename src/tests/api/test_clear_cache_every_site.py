"""clear_cache with neither a request nor a site clears every active site.

Its fallback looked the sites up with `site__is_null`, a lookup Django does not
have: the query raised FieldError, and a caller clearing a site-independent
cache got a 500 after its write had already succeeded.
"""
import uuid

import pytest
from django.core.cache import cache

pytestmark = [pytest.mark.asyncio]


@pytest.fixture
def sites(transactional_db):
    from django.contrib.sites.models import Site

    from facility.models import Organization

    suffix = uuid.uuid4().hex[:8]
    made = {}
    for name, active in (("first", True), ("second", True), ("dormant", False)):
        site = Site.objects.create(domain=f"{name}-{suffix}.test", name=name)
        Organization.objects.create(name=f"{name}-{suffix}", site=site, active=active)
        made[name] = site
    return made


async def test_every_active_site_s_key_is_cleared(sites):
    from api.utils import clear_cache

    endpoint = f"v2:test-{uuid.uuid4().hex[:8]}"
    for site in sites.values():
        cache.set(f"{endpoint}:{site.domain}", "cached")

    await clear_cache(endpoint)

    assert cache.get(f"{endpoint}:{sites['first'].domain}") is None
    assert cache.get(f"{endpoint}:{sites['second'].domain}") is None
    assert cache.get(f"{endpoint}:{sites['dormant'].domain}") == "cached"
    cache.delete(f"{endpoint}:{sites['dormant'].domain}")
