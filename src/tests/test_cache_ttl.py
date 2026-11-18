"""How long a cached API response lives, and who decides.

Every cached endpoint resolves its TTL the same way: look for a row in the
``TTL`` table for *this endpoint and this site*, and fall back to a constant in
the code when there is none. Both halves of that sentence have bitten us.

Why this is a test
------------------
A wrong TTL does not fail. It makes the site *slower*, intermittently, in a way
that reads as a network problem — which is exactly how it was found.

On 2026-08-14 a link check of staging.annuaire.medica.im reported 66 broken
links, 65 of them timeouts on pages that answered in 0.3s when fetched one at a
time. The site's ``v2:entries`` TTL was 300s and a full crawl takes ~100s, so
whether the run passed depended on whether the key happened to expire while the
crawler was mid-flight. Measured on that server:

===========================  ========
warm cache                    0.3s
cold, one request             4.9s
cold, four concurrent        12.5s each
===========================  ========

Four parallel requests into an expired key do not share the rebuild; each one
regenerates the same dataset. So the cost of an expiry is not the 4.9s of one
miss, it is that multiplied by everything that arrives during the gap. A short
TTL turns a rare stampede into a frequent one.

The tests below pin the three things that were wrong:

1. the default is long enough that a miss is rare (it was 60s),
2. a TTL of ``0`` means *zero*, and is not silently replaced by the default,
3. a missing TTL row is reported, so a site running on the fallback can be
   found before it is found by a crawler.
"""
import pytest

from api import utils
from api.serializers import allentries
from api.routers import public_facilities, situations


# The floor below which a TTL is not worth having. A miss costs seconds of
# regeneration on the larger sites, and anything that expires faster than a
# page is read spends most of its life cold.
MINIMUM_SENSIBLE_TTL = 300


@pytest.mark.no_db
class TestDefaults:
    """The constant used when a site has no TTL row of its own."""

    def test_entries_default_is_not_shorter_than_the_minimum(self):
        # v2:entries is the big one — 560 entries on the largest site, and the
        # endpoint every page of the directory goes through. At the original 60
        # it expired roughly once a minute, and every expiry under load was a
        # stampede.
        assert allentries.TTL >= MINIMUM_SENSIBLE_TTL

    def test_public_facilities_default_is_not_shorter_than_the_minimum(self):
        assert public_facilities.DEFAULT_TTL >= MINIMUM_SENSIBLE_TTL

    def test_situations_default_is_not_shorter_than_the_minimum(self):
        # This one was already 3600 and never caused trouble; asserted so the
        # three defaults cannot drift apart again unnoticed.
        assert situations.TTL >= MINIMUM_SENSIBLE_TTL

    def test_the_defaults_agree_with_each_other(self):
        # Three constants in three files, all answering "how long should a
        # cached response live when nobody has said". They were 60, 60 and
        # 3600. A single name means changing the answer is one edit.
        assert allentries.TTL == public_facilities.DEFAULT_TTL == utils.DEFAULT_TTL


@pytest.mark.no_db
class TestZeroIsNotMissing:
    """``0`` means do not cache. It must not be read as "no value"."""

    def test_zero_ttl_is_returned_as_zero(self):
        # The call sites read `await get_ttl(...) or TTL`, and 0 is falsy in
        # Python — so a row saying "do not cache this" was silently turned into
        # the default. resolve_ttl exists to make that distinction, since `or`
        # cannot.
        assert utils.resolve_ttl(0, default=3600) == 0

    def test_none_falls_back_to_the_default(self):
        assert utils.resolve_ttl(None, default=3600) == 3600

    def test_a_real_value_wins_over_the_default(self):
        assert utils.resolve_ttl(120, default=3600) == 120


@pytest.mark.asyncio
@pytest.mark.no_db
class TestAMissingRowIsReported:
    """A site with no TTL row runs on the default. That should be visible."""

    async def test_missing_ttl_logs_a_warning(self, monkeypatch, caplog):
        # .afirst() returns None when nothing matches — it does not raise
        # DoesNotExist. The original code guarded for the exception instead, so
        # the "not found" branch could never run and a site quietly running on
        # the fallback left no trace at all. staging.santelyon3.fr had no rows
        # for months and nobody knew.
        class _NoRow:
            async def afirst(self):
                return None

        monkeypatch.setattr(
            utils.TTL, "objects", type("M", (), {"filter": staticmethod(lambda **kw: _NoRow())})
        )

        async def _site(_request):
            return "example.test"

        monkeypatch.setattr(utils, "get_site_from_request", _site)

        request = type(
            "R", (), {"scope": {"route": type("Rt", (), {"path": "/entries"})()}}
        )()

        with caplog.at_level("WARNING"):
            result = await utils.get_ttl("v2", request)

        assert result is None
        assert any(
            "no ttl row" in r.getMessage().lower()
            for r in caplog.records
        ), f"a missing TTL row should be logged; got {[r.getMessage() for r in caplog.records]}"
