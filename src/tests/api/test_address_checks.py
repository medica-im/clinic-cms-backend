"""Catching a bad address before anything is sent.

An invitation to "jean@gmial.com" bounces, and only then does anyone learn
the address was mistyped. Typed or imported, an address is checked first:

* a typo in a common mail domain gets a suggestion ("gmial.com" ->
  "gmail.com"), applied with one click;
* a domain that cannot receive mail (no MX record, and no address to fall
  back on) is flagged;
* an address already known to be bad (mailer.suppression) says why.

Warnings, never refusals: the administrator decides. And never on
uncertainty -- a DNS timeout is not evidence the domain is wrong.

POST /api/v2/mail/check-addresses for the create form, POST
/api/v2/batch-invitees/check for a spreadsheet, before it is sent. Provider-
neutral: mailer.addresscheck asks DNS, not the mail service.
"""
import io
import json
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import dns.exception
import dns.resolver
import pytest
from asgiref.sync import sync_to_async

from mailer import addresscheck

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]


@contextmanager
def fake_dns(answers):
    """answers: domain -> 'mx' | 'a' | 'none' | 'timeout'."""
    def resolve(name, rtype, *args, **kwargs):
        kind = answers.get(name, "mx")
        if kind == "timeout":
            raise dns.exception.Timeout()
        if (rtype == "MX" and kind == "mx") or (rtype in ("A", "AAAA") and kind == "a"):
            return ["answer"]
        raise dns.resolver.NoAnswer()

    addresscheck.receives_mail.cache_clear()
    with patch("mailer.addresscheck.dns.resolver.resolve", side_effect=resolve):
        yield


async def check(address, organization=None):
    return await sync_to_async(addresscheck.check)(address, organization)


class TestTypos:
    @pytest.mark.parametrize("typed,suggested", [
        ("jean@gmial.com", "jean@gmail.com"),
        ("jean@gmail.con", "jean@gmail.com"),
        ("jean@wanado.fr", "jean@wanadoo.fr"),
        ("jean@hotmial.fr", "jean@hotmail.fr"),
        ("jean@orange.fe", "jean@orange.fr"),
    ])
    async def test_a_common_domain_mistyped_gets_a_suggestion(self, typed, suggested):
        with fake_dns({}):
            assert (await check(typed))["suggestion"] == suggested

    @pytest.mark.parametrize("address", ["jean@gmail.com", "jean@orange.fr", "jean@cpts-lyon3.fr"])
    async def test_a_right_or_unknown_domain_gets_none(self, address):
        with fake_dns({}):
            assert (await check(address))["suggestion"] is None


class TestTheDomain:
    async def test_without_mx_or_address_it_cannot_receive_mail(self):
        with fake_dns({"nowhere.example": "none"}):
            assert (await check("jean@nowhere.example"))["problem"] == "no_mail_domain"

    async def test_an_address_record_is_enough(self):
        """Mail falls back to the A record when there is no MX (RFC 5321)."""
        with fake_dns({"small.example": "a"}):
            assert (await check("jean@small.example"))["problem"] is None

    async def test_a_timeout_is_not_evidence(self):
        with fake_dns({"slow.example": "timeout"}):
            assert (await check("jean@slow.example"))["problem"] is None

    async def test_not_an_address_at_all(self):
        with fake_dns({}):
            assert (await check("jean.medica.im"))["problem"] == "invalid"


class TestKnownAddresses:
    async def test_one_that_bounced_says_so(self):
        from mailer import suppression

        await sync_to_async(suppression.record)("gone@medica.im", "bounced", detail="550")
        with fake_dns({}):
            assert (await check("Gone@Medica.im"))["problem"] == "bounced"


class TestTheEndpoints:
    async def test_checking_typed_addresses(self, versioned_client, patch_jwt, jwt_administrator, site):
        with patch_jwt(jwt_administrator), fake_dns({"nowhere.example": "none"}), \
                patch("api.routers.mail_checks.authorize_api", new_callable=AsyncMock), \
                patch("api.routers.mail_checks.get_site_from_request", new_callable=AsyncMock, return_value=site):
            r = await versioned_client.post(
                "/api/v2/mail/check-addresses", json={"emails": ["jean@gmial.com", "ok@gmail.com", "x@nowhere.example"]},
            )
        assert r.status_code == 200, r.text
        by_email = {c["email"]: c for c in r.json()}
        assert by_email["jean@gmial.com"]["suggestion"] == "jean@gmail.com"
        assert by_email["ok@gmail.com"] == {"email": "ok@gmail.com", "suggestion": None, "problem": None}
        assert by_email["x@nowhere.example"]["problem"] == "no_mail_domain"

    async def test_guarded_like_the_invitations(self, versioned_client, patch_jwt, jwt_staff):
        from fastapi import HTTPException

        with patch_jwt(jwt_staff), patch("api.routers.mail_checks.authorize_api", new_callable=AsyncMock,
                                         side_effect=HTTPException(status_code=403)):
            r = await versioned_client.post("/api/v2/mail/check-addresses", json={"emails": ["a@b.c"]})
        assert r.status_code == 403

    async def test_checking_a_spreadsheet_before_sending(self, versioned_client, patch_jwt, jwt_administrator, site):
        csv = b"email\njean@gmial.com\nok@gmail.com\n"
        with patch_jwt(jwt_administrator), fake_dns({}), \
                patch("api.routers.batch_invitees.authorize_api", new_callable=AsyncMock), \
                patch("api.routers.batch_invitees.get_site_from_request", new_callable=AsyncMock, return_value=site):
            r = await versioned_client.post(
                "/api/v2/batch-invitees/check",
                files={"file": ("people.csv", io.BytesIO(csv), "text/csv")},
                data={"mapping_json": json.dumps({"email_column": "email"})},
            )
        assert r.status_code == 200, r.text
        assert r.json() == [{"row": 1, "email": "jean@gmial.com", "suggestion": "jean@gmail.com", "problem": None}]
