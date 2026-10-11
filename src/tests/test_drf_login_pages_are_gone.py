"""DRF's browsable-API login and logout pages are not served.

rest_framework.urls is Django's username/password login, for browsing the
API in a browser. There have been no password accounts since dj-rest-auth
went (6a0897e): the form could log nobody in and was only one more public
page. directory.urls, mounted twice, also made its namespace ambiguous
(urls.W005 on `directory:rest_framework`).
"""

import pytest
from django.core.checks import run_checks
from django.test import Client

MOUNTS = ["/api/", "/api/v1/directory/", "/api/v1/workforce/", "/api/v1/opengraph/", "/api/v1/heatwave/"]


@pytest.mark.parametrize("mount", MOUNTS)
@pytest.mark.parametrize("page", ["login/", "logout/"])
def test_the_page_is_not_found(site, mount, page):
    assert Client().get(f"{mount}api-auth/{page}").status_code == 404


@pytest.mark.no_db
def test_no_rest_framework_namespace_is_ambiguous():
    ambiguous = [m.msg for m in run_checks() if m.id == "urls.W005" and "rest_framework" in m.msg]
    assert ambiguous == []
