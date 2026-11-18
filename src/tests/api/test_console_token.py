"""The console's credential: a bearer token standing for one account.

The console (a private app, outside every site) writes effector types and
their labels on each backend. It has no session cookie there, so it presents
a token: `Authorization: Bearer console_…`. A live token makes the request
that account's, so authorize_api and the role lookup apply unchanged — the
console can do exactly what that account can, no more.

* Stored hashed: the database never holds a usable token.
* Revocable; a revoked or unknown console token is a 401, never anonymous.
* A session cookie wins over a token, as with the clone token.
"""
import hashlib

import pytest
from fastapi import HTTPException
from starlette.requests import Request

pytestmark = pytest.mark.django_db

SUB = "1234567890"


def request(authorization: str | None = None, cookie: str | None = None) -> Request:
    headers = []
    if authorization:
        headers.append((b"authorization", authorization.encode()))
    if cookie:
        headers.append((b"cookie", cookie.encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "query_string": b""})


@pytest.fixture
def token(transactional_db) -> str:
    from access.models import ConsoleToken

    return ConsoleToken.issue(label="console", sub=SUB)


class TestTheToken:
    def test_it_stands_for_its_account(self, token):
        from api.auth import JWT

        assert JWT(request(f"Bearer {token}"))["providerAccountId"] == SUB

    def test_the_optional_dependency_reads_it_too(self, token):
        from api.auth import check_cookie_jwt

        assert check_cookie_jwt(request(f"Bearer {token}"))["providerAccountId"] == SUB

    def test_only_its_hash_is_stored(self, token):
        from access.models import ConsoleToken

        row = ConsoleToken.objects.get()
        assert token not in (row.token_hash, row.label, row.sub)
        assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()

    def test_its_use_is_recorded(self, token):
        from access.models import ConsoleToken
        from api.auth import JWT

        JWT(request(f"Bearer {token}"))

        assert ConsoleToken.objects.get().last_used is not None


class TestRefusals:
    def test_a_revoked_token_is_refused(self, token):
        from access.models import ConsoleToken
        from api.auth import JWT

        ConsoleToken.objects.update(revoked=True)

        with pytest.raises(HTTPException) as refused:
            JWT(request(f"Bearer {token}"))
        assert refused.value.status_code == 401

    @pytest.mark.parametrize("dependency", ["JWT", "check_cookie_jwt"])
    def test_an_unknown_console_token_is_refused_not_anonymous(self, transactional_db, dependency):
        import api.auth

        with pytest.raises(HTTPException) as refused:
            getattr(api.auth, dependency)(request("Bearer console_not-a-real-one"))
        assert refused.value.status_code == 401


class TestIssuing:
    def test_the_command_prints_a_working_token(self, transactional_db, capsys):
        from unittest.mock import patch

        from django.core.management import call_command

        from api.auth import JWT

        with patch("access.management.commands.issue_console_token.account_sub", return_value=SUB):
            call_command("issue_console_token", "--label", "console", "--email", "me@example.org")

        printed = capsys.readouterr().out.strip().splitlines()[-1]
        assert printed.startswith("console_")
        assert JWT(request(f"Bearer {printed}"))["providerAccountId"] == SUB
