"""directory.urls is served under /api/v1/directory/ only.

It was also mounted at the unversioned /api/, under the same namespace
(urls.W005: reverse() could build only one of the two). Nothing reached that
second mount: nginx sends only /admin/ and /api/v1/ to Django, a bare /api/
goes to the SvelteKit server, and the frontend calls /api/v1/directory/.
"""

import pytest
from django.core.checks import run_checks
from django.urls import Resolver404, resolve

pytestmark = pytest.mark.no_db

VIEWS = ["", "timestamps"]


@pytest.mark.parametrize("view", VIEWS)
def test_served_under_the_versioned_prefix(view):
    assert resolve(f"/api/v1/directory/{view}")


@pytest.mark.parametrize("view", VIEWS)
def test_not_served_under_the_bare_prefix(view):
    with pytest.raises(Resolver404):
        resolve(f"/api/{view}")


def test_no_url_namespace_is_ambiguous():
    assert [m.msg for m in run_checks() if m.id == "urls.W005"] == []
