"""The /api/v1/opengraph/ mount is gone, and stays gone.

The site's sharing card is served by FastAPI at /api/v2/opengraph
(tests/api/test_opengraph_v2.py), which the frontend has called since the
layout moved off the Django route. Two implementations of one answer would
drift: only the v2 one invalidates its cache when a card is edited.

The app stays: its TwitterCard model and cache key are the v2 route's. Only
the Django view, its serializer and its URL conf are retired.
"""

import importlib.util

import pytest
from django.urls import resolve
from django.urls.exceptions import Resolver404


@pytest.mark.parametrize("path", ["/api/v1/opengraph/", "/api/v1/opengraph"])
def test_the_url_does_not_resolve(path):
    with pytest.raises(Resolver404):
        resolve(path)


@pytest.mark.parametrize(
    "module", ["opengraph.urls", "opengraph.views", "opengraph.serializers"]
)
def test_the_module_that_served_it_is_removed(module):
    assert importlib.util.find_spec(module) is None


def test_what_the_v2_route_reads_remains():
    from opengraph.cache import opengraph_cache_key
    from opengraph.models import TwitterCard

    assert opengraph_cache_key and TwitterCard
