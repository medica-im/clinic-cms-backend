"""No email-and-password account endpoints.

Users sign in with Google (Auth.js in the frontend); there are no passwords to
log in with or reset. dj-rest-auth's endpoints (login, logout, password
change and reset by email) were added in June 2025 for password accounts; the
frontend pages calling them were removed in August 2025, and the include had
been answering 500 since. Removed rather than left reachable.
"""
import pytest
from django.urls import Resolver404, resolve


@pytest.mark.parametrize("path", [
    "/dj-rest-auth/login/",
    "/dj-rest-auth/password/reset/",
    "/dj-rest-auth/password/reset/confirm/",
])
def test_the_password_endpoints_are_gone(path):
    with pytest.raises(Resolver404):
        resolve(path)
