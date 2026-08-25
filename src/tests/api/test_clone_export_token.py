"""The credential that lets one deployment read another's entries.

A clone token is a bearer credential for a superuser's whole directory —
practitioners' names, addresses, phone numbers, emails. Every property below is
what keeps that bounded: who it names, which instance may present it, which
entries it reaches, how long it lives, and how it is revoked.

Signed with a key *derived* from AUTH_SECRET rather than AUTH_SECRET itself, so
a fault here can never mint something a session decoder would accept. The first
test is that derivation, because it is invisible in behaviour and would survive
any amount of manual testing.
"""
import hashlib
import os

import pytest
from django.core import signing
from fastapi import HTTPException

from api.serializers.clone import token as clone_token

pytestmark = pytest.mark.django_db

SUB = "google-sub-of-the-superuser"
SRC = "santelyon3.fr"
TARGET = "https://dev.santelyon3.fr"
DIR = "santelyon3"


def _mint(**over):
    kwargs = dict(sub=SUB, source_host=SRC, target_origin=TARGET, directory=DIR,
                  org_entry="orgentryuid", entry_uids=None)
    kwargs.update(over)
    return clone_token.mint(**kwargs)[0]


class TestTheSigningKey:
    def test_it_is_not_the_session_secret(self):
        """A clone token must not be signable with AUTH_SECRET alone.

        If it were, every property of the session cookie and every property of
        this token would share one key: one flaw would compromise both.
        """
        token = _mint()
        with pytest.raises(signing.BadSignature):
            signing.loads(token, key=os.getenv("AUTH_SECRET") or "",
                          salt=clone_token.SALT, max_age=clone_token.TTL_SECONDS)

    def test_it_is_derived_from_it(self):
        """Derived, so nothing new has to be configured on either instance."""
        expected = hashlib.sha256(
            f"{clone_token.SALT}:{os.getenv('AUTH_SECRET')}".encode()
        ).hexdigest()
        claims = signing.loads(_mint(), key=expected, salt=clone_token.SALT,
                               max_age=clone_token.TTL_SECONDS)
        assert claims["sub"] == SUB


class TestWhoAndWhereItIsValid:
    def test_the_minting_instance_accepts_it(self):
        claims = clone_token.read(_mint(), request_host=SRC)
        assert claims.sub == SUB
        assert claims.directory == DIR
        assert claims.org_entry == "orgentryuid"

    def test_another_instance_refuses_it(self):
        """A token names the instance that minted it.

        Without this, a token leaked from staging would be presented to
        production, which can verify a signature it made itself.
        """
        with pytest.raises(HTTPException) as e:
            clone_token.read(_mint(), request_host="production.example.test")
        assert e.value.status_code == 401

    def test_a_tampered_token_is_refused(self):
        token = _mint()
        with pytest.raises(HTTPException) as e:
            clone_token.read(token[:-4] + "AAAA", request_host=SRC)
        assert e.value.status_code == 401

    def test_rubbish_is_refused(self):
        with pytest.raises(HTTPException) as e:
            clone_token.read("not-a-token", request_host=SRC)
        assert e.value.status_code == 401


class TestWhatItReaches:
    def test_a_directory_token_reaches_any_entry_in_it(self):
        claims = clone_token.read(_mint(entry_uids=None), request_host=SRC)
        assert claims.allows("any-uid-at-all")

    def test_a_scoped_token_reaches_only_its_entries(self):
        """The narrower scope is the one the UI mints.

        A superuser picking three entries should not hand over a credential for
        the other four hundred.
        """
        claims = clone_token.read(_mint(entry_uids=["a", "b"]), request_host=SRC)
        assert claims.allows("a")
        assert not claims.allows("c")


class TestHowItStops:
    def test_it_expires(self, monkeypatch):
        token = _mint()
        # Read it back as though the TTL had passed, rather than sleeping.
        monkeypatch.setattr(clone_token, "TTL_SECONDS", -1)
        with pytest.raises(HTTPException) as e:
            clone_token.read(token, request_host=SRC)
        assert e.value.status_code == 401

    def test_burning_it_stops_it_immediately(self):
        """A batch that ends should not leave a live credential behind."""
        token = _mint()
        assert clone_token.read(token, request_host=SRC).sub == SUB
        clone_token.burn(token, request_host=SRC)
        with pytest.raises(HTTPException) as e:
            clone_token.read(token, request_host=SRC)
        assert e.value.status_code == 401

    def test_it_runs_out_of_uses(self):
        """A use cap bounds what one leaked token can pull.

        The TTL alone would let a token that escapes mid-batch read the whole
        directory for fifteen minutes.
        """
        token = _mint()
        for _ in range(clone_token.MAX_USES):
            clone_token.read(token, request_host=SRC)
        with pytest.raises(HTTPException) as e:
            clone_token.read(token, request_host=SRC)
        assert e.value.status_code == 401


class TestATokenIsNotTransferable:
    """A token is for one person, one source, one target — not a passkey.

    These are the properties that stop a token doing more than the batch it was
    minted for, if it is ever seen by someone else: in a shared screenshot, a
    pasted bug report, or a proxy log.
    """

    def test_it_names_the_person_it_was_minted_for(self):
        """The sub travels, so the source can re-check the role on every use.

        Without it the token would authorise *anyone* holding it for fifteen
        minutes, rather than acting as that superuser's credential.
        """
        claims = clone_token.read(_mint(sub="somebody-specific"), request_host=SRC)
        assert claims.sub == "somebody-specific"

    def test_it_names_the_target_it_was_minted_for(self):
        """Audience-bound, so a token intercepted in transit is not a free pass.

        Not enforced at read time — the source only ever sees its own host — but
        carried so an audit can say which target a token was issued to, and so a
        future check has the field to work with.
        """
        import django.core.signing as signing
        import hashlib, os
        key = hashlib.sha256(f"{clone_token.SALT}:{os.getenv('AUTH_SECRET')}".encode()).hexdigest()
        raw = signing.loads(_mint(target_origin="https://only-this-one.test"),
                            key=key, salt=clone_token.SALT, max_age=clone_token.TTL_SECONDS)
        assert raw["aud"] == "https://only-this-one.test"

    def test_two_tokens_are_not_interchangeable(self):
        """Each mint gets its own jti, so burning one does not burn the other.

        A shared identifier would mean ending one batch silently killed another
        superuser's in-flight clone.
        """
        a, b = _mint(), _mint()
        assert a != b
        clone_token.burn(a, request_host=SRC)
        assert clone_token.read(b, request_host=SRC).sub == SUB
