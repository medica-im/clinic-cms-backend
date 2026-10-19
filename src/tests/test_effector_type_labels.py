"""The effector-type label dictionary, and the TTL lookup behind it.

`get_effector_type_labels` builds the structure the frontend reads to render a
type in the right gender and number: {uid: {"S"|"P": {"F"|"M"|"N": label}}}.
Every slot exists for every uid, holding None where no Label row was authored,
so a caller can index into it without guarding each level.

Nothing covered this. The one existing label test — test_effector_type_raw_label
— exercises `createEffectorTypeResources`, a different path that never touches
this dictionary, and the endpoint in front of it had no test at all.

Three layers are covered, deliberately:

- the builder, `get_effector_type_labels`, for the shape it constructs;
- the TTL lookup behind the view's caching;
- the JSON response itself, asserted against rows actually in the database.

That last layer is the contract the frontend depends on — src/lib/interfaces
declares `Record<string, {S: {F,M,N}, P: {F,M,N}}>` with nullable strings — and
it is the layer that must survive the move to a v2 FastAPI router. A test that
only calls the Python function cannot see a serialisation change: None must
arrive as null, uid keys must stay strings, and every authored row must be
present. These tests are written so the v2 implementation can be pointed at
them unchanged.
"""
import uuid

import pytest

pytestmark = pytest.mark.django_db


TERM_TYPE = "name"
LANGUAGE = "fr"


@pytest.fixture
def genders(transactional_db):
    """The three GrammaticalGender rows the builder looks up by name.

    It fetches all three unconditionally, so a database missing any of them
    logs an error and then raises NameError on the undefined local. These rows
    are a precondition of the function, not something under test.
    """
    from accounts.models import GrammaticalGender

    codes = {"feminine": "F", "masculine": "M", "neutral": "N"}
    rows = {}
    for name, code in codes.items():
        rows[name], _ = GrammaticalGender.objects.get_or_create(
            name=name,
            defaults={"label": name.capitalize(), "code": code},
        )
        # get_or_create matches on name alone: a row left over from another
        # test with the wrong code would otherwise silently reshape the answer.
        if rows[name].code != code:
            rows[name].code = code
            rows[name].save()
    return rows


def make_label(uid, gender, number, label, language=LANGUAGE, term_type=TERM_TYPE):
    from directory.models.core import Label

    row = Label.objects.create(
        uid=uid,
        label=label,
        grammatical_number=number,
        language=language,
        term_type=term_type,
    )
    row.gender.add(gender)
    return row


def labels_in(language=LANGUAGE, term_type=TERM_TYPE) -> dict:
    from asgiref.sync import async_to_sync
    from api.serializers.effector_type_labels import get_effector_type_labels

    return async_to_sync(get_effector_type_labels)(language, term_type).model_dump()


class TestTheLabelDictionary:
    def test_a_label_lands_under_its_number_and_gender(self, genders):
        uid = uuid.uuid4()
        make_label(uid, genders["feminine"], "S", "infirmière")

        dictionary = labels_in()

        assert dictionary[uid.hex]["S"]["F"] == "infirmière"

    def test_every_slot_is_present_even_when_unauthored(self, genders):
        """The frontend indexes without guarding, so the shape is the contract.

        One authored label must not leave the other five slots missing: it
        leaves them None.
        """
        uid = uuid.uuid4()
        make_label(uid, genders["feminine"], "S", "infirmière")

        entry = labels_in()[uid.hex]

        assert set(entry) == {"S", "P"}
        for number in ("S", "P"):
            assert set(entry[number]) == {"F", "M", "N"}
        assert entry["S"]["M"] is None
        assert entry["P"]["F"] is None

    def test_singular_and_plural_are_kept_apart(self, genders):
        uid = uuid.uuid4()
        make_label(uid, genders["masculine"], "S", "infirmier")
        make_label(uid, genders["masculine"], "P", "infirmiers")

        entry = labels_in()[uid.hex]

        assert entry["S"]["M"] == "infirmier"
        assert entry["P"]["M"] == "infirmiers"

    def test_the_uid_key_is_hex_without_hyphens(self, genders):
        """Neo4j node uids are stored hex, and the frontend keys on that form.

        A UUIDField renders with hyphens under str(); the dictionary must not.
        """
        uid = uuid.uuid4()
        make_label(uid, genders["neutral"], "S", "CPTS")

        keys = labels_in()

        assert uid.hex in keys
        assert str(uid) not in keys
        assert "-" not in uid.hex

    def test_another_language_is_not_mixed_in(self, genders):
        """One dictionary is built per language; rows in another must not leak."""
        uid = uuid.uuid4()
        make_label(uid, genders["neutral"], "S", "nurse", language="en")

        dictionary = labels_in()

        # The uid still keys the dictionary — it comes from the term_type
        # filter, which ignores language — but the English label must not fill
        # the French slot.
        assert dictionary[uid.hex]["S"]["N"] is None

    def test_another_term_type_is_not_listed_at_all(self, genders):
        """Unlike language, term_type decides which uids appear as keys."""
        uid = uuid.uuid4()
        make_label(uid, genders["neutral"], "S", "CPTS", term_type="label")

        assert uid.hex not in labels_in()


class TestZeroReachesTheCache:
    """A TTL of 0 must arrive at cache.set as 0, not as the default.

    The v1 view read `get_ttl(...) or TTL`, and 0 is falsy in Python: a row
    saying "never cache this" was silently rewritten to 60 seconds. resolve_ttl
    exists for exactly this (test_cache_ttl.TestZeroIsNotMissing pins the
    helper itself); these watch the boundary — the timeout the endpoint hands
    to cache.set — because that is where the bug was visible.
    """

    @pytest.fixture
    def timeouts(self, monkeypatch):
        from django.core.cache import cache

        recorded = []
        monkeypatch.setattr(cache, "get", lambda key, default=None: None)
        monkeypatch.setattr(cache, "set", lambda key, value, timeout=None: recorded.append(timeout))
        return recorded

    def test_a_zero_ttl_is_not_replaced_by_the_default(self, directory_site, genders, timeouts):
        from directory.models.api import Endpoint, TTL

        endpoint, _ = Endpoint.objects.get_or_create(name="v2:effector-type-labels")
        TTL.objects.update_or_create(endpoint=endpoint, site=directory_site, defaults={"ttl": 0})

        get_v2()

        assert timeouts == [0]

    def test_an_absent_row_still_falls_back_to_the_default(self, directory_site, genders, timeouts):
        from api.routers.effector_type_labels import TTL

        get_v2()

        assert timeouts == [TTL]


# ---------------------------------------------------------------------------
# The JSON response
# ---------------------------------------------------------------------------
#
# Everything above tests Python objects. These tests read the serialised body a
# client actually receives, because that is the contract — and because the
# builder and the response can diverge: None has to arrive as null, uid keys
# have to survive as strings, and a caching layer sits between the two.
#
# The v1 Django endpoint this replaced is gone; these assertions, written to
# hold for both while they coexisted, now hold the v2 router to the same body.

V2_URL = "/api/v2/effector-type-labels"


@pytest.fixture
def directory_site(transactional_db, site):
    """A Site with the Organization and Directory the view walks to find a language.

    The view resolves `directory.site.organization.language`, so a request that
    never reaches the database for these will 500 long before it serialises
    anything. Built for real rather than monkeypatched: these tests are about
    what a genuine request returns.
    """
    from django.contrib.sites.models import Site
    from directory.models.core import Directory
    from facility.models import Organization

    directory, _ = Directory.objects.get_or_create(
        name="testdirectory",
        defaults={"display_name": "Test Directory", "site": site},
    )
    if directory.site_id != site.id:
        directory.site = site
        directory.save()
    Organization.objects.update_or_create(
        site=site,
        defaults={
            "name": "test-org",
            "formatted_name": "Test Org",
            "language": LANGUAGE,
            "directory": directory,
        },
    )
    return site


@pytest.fixture
def no_cache(monkeypatch):
    """Serve every request from the database.

    The view returns a cached body verbatim when one exists, so without this a
    dict cached by an earlier test would be asserted against this test's rows.
    """
    from django.core.cache import cache

    monkeypatch.setattr(cache, "get", lambda key, default=None: None)
    monkeypatch.setattr(cache, "set", lambda key, value, timeout=None: None)


class _Response:
    """The response, reduced to what these tests assert on."""

    def __init__(self, response):
        self.status_code = response.status_code
        self.content_type = response.headers.get("content-type", "")
        self.content = response.content

    def json(self):
        import json

        return json.loads(self.content)


@pytest.fixture
def api(directory_site, no_cache, genders):
    """Fetches the label resource from the v2 router, as the frontend does."""
    return lambda: _Response(get_v2())


class TestTheJSONResponse:
    def test_it_answers_200_with_json(self, api):
        response = api()

        assert response.status_code == 200
        assert response.content_type.startswith("application/json")

    def test_an_authored_label_appears_in_the_body(self, api, genders):
        uid = uuid.uuid4()
        make_label(uid, genders["feminine"], "S", "infirmière")
        make_label(uid, genders["masculine"], "S", "infirmier")
        make_label(uid, genders["feminine"], "P", "infirmières")

        body = api().json()

        assert body[uid.hex] == {
            "S": {"F": "infirmière", "M": "infirmier", "N": None},
            "P": {"F": "infirmières", "M": None, "N": None},
        }

    def test_unauthored_slots_serialise_as_null(self, api, genders):
        """None must cross the JSON boundary as null, not be dropped.

        The frontend types these as `string|null` and indexes without guarding,
        so a missing key is a TypeError there rather than a falsy value.
        """
        import json

        uid = uuid.uuid4()
        make_label(uid, genders["neutral"], "S", "CPTS")

        raw = api().content.decode()
        entry = json.loads(raw)[uid.hex]

        assert entry["S"]["F"] is None
        assert '"F": null' in raw or '"F":null' in raw
        assert set(entry["S"]) == {"F", "M", "N"}

    def test_every_authored_uid_is_present_and_no_others(self, api, genders):
        """The body reflects the database: all name rows, nothing invented."""
        from directory.models.core import Label

        for label in ("un", "deux", "trois"):
            make_label(uuid.uuid4(), genders["neutral"], "S", label)
        make_label(uuid.uuid4(), genders["neutral"], "S", "short", term_type="label")

        body = api().json()

        expected = {
            u.hex
            for u in Label.objects.filter(term_type=TERM_TYPE).values_list(
                "uid", flat=True
            )
        }
        assert set(body) == expected
        assert len(body) == 3

    def test_keys_are_hex_strings(self, api, genders):
        """JSON object keys are strings; they must be the hex form Neo4j uses."""
        uid = uuid.uuid4()
        make_label(uid, genders["neutral"], "S", "CPTS")

        body = api().json()

        assert uid.hex in body
        assert all(isinstance(k, str) and "-" not in k for k in body)

    def test_the_whole_body_matches_the_database(self, api, genders):
        """One assertion over the entire response, built from the rows directly.

        The per-field tests above say the pieces are right; this one says there
        is nothing else in the body — no extra key, no dropped uid, no reshaped
        nesting. It is the assertion to keep pointed at v2.
        """
        from directory.models.core import Label

        first, second = uuid.uuid4(), uuid.uuid4()
        make_label(first, genders["feminine"], "S", "infirmière")
        make_label(first, genders["feminine"], "P", "infirmières")
        make_label(second, genders["neutral"], "S", "CPTS")

        body = api().json()

        expected = {}
        for row in Label.objects.filter(term_type=TERM_TYPE, language=LANGUAGE):
            slot = expected.setdefault(
                row.uid.hex,
                {"S": {"F": None, "M": None, "N": None},
                 "P": {"F": None, "M": None, "N": None}},
            )
            for gender in row.gender.all():
                slot[row.grammatical_number][gender.code] = row.label

        assert body == expected

    def test_an_empty_database_is_an_empty_object(self, api):
        """No rows is `{}` — not null, not an error.

        The frontend does `page.data.labels[uid]` against whatever arrives; a
        null body would break every consumer rather than render nothing.
        """
        body = api().json()

        assert body == {}


# ---------------------------------------------------------------------------
# One answer per language
# ---------------------------------------------------------------------------
#
# Labels belong to the whole backend; a site only decides which language it is
# answered in. So the dictionary is built and cached once per language, and
# `?language=` asks for one by name: the console reads each language in one
# request instead of type by type (115 requests per backend, which staging's
# rate limit refused). Every write to labels clears every language, in both
# API versions.


def get_v2(params=None):
    import asyncio

    async def _get():
        from httpx import AsyncClient
        from tests.api.conftest import _StripPrefixTransport
        from main import app

        async with AsyncClient(
            transport=_StripPrefixTransport(app=app), base_url="http://testserver"
        ) as ac:
            return await ac.get(V2_URL, params=params)

    return asyncio.run(_get())


@pytest.fixture
def own_cache(monkeypatch):
    """A cache of the test's own.

    The per-language keys are the dev backend's too (tests share its Redis):
    a test must never leave its rows where the dev sites read them.
    """
    from django.core.cache import cache

    store = {}
    monkeypatch.setattr(cache, "get", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr(cache, "set", lambda key, value, timeout=None: store.__setitem__(key, value))
    monkeypatch.setattr(cache, "delete", lambda key: store.pop(key, None) is not None)
    monkeypatch.setattr(cache, "delete_many", lambda keys: [store.pop(k, None) for k in keys])
    return store


LABEL_CACHE_KEYS = {f"v2:effector-type-labels:{language}" for language in ("fr", "en")}


class TestOneAnswerPerLanguage:
    def test_a_language_asked_for_is_answered_in_it(self, directory_site, own_cache, genders):
        uid = uuid.uuid4()
        make_label(uid, genders["feminine"], "S", "infirmière")
        make_label(uid, genders["feminine"], "S", "nurse", language="en")

        assert get_v2({"language": "en"}).json()[uid.hex]["S"]["F"] == "nurse"

    def test_a_site_is_answered_in_its_own_language(self, directory_site, own_cache, genders):
        uid = uuid.uuid4()
        make_label(uid, genders["feminine"], "S", "infirmière")
        make_label(uid, genders["feminine"], "S", "nurse", language="en")

        assert get_v2().json()[uid.hex]["S"]["F"] == "infirmière"

    def test_it_is_cached_once_per_language_not_per_site(self, directory_site, own_cache, genders):
        make_label(uuid.uuid4(), genders["neutral"], "S", "pharmacie")

        get_v2()
        get_v2({"language": "en"})

        assert set(own_cache) == {"v2:effector-type-labels:fr", "v2:effector-type-labels:en"}

    def test_a_site_and_a_language_asked_for_share_one_answer(self, directory_site, own_cache, genders):
        make_label(uuid.uuid4(), genders["neutral"], "S", "pharmacie")
        cached_by_the_site = get_v2().json()

        assert get_v2({"language": "fr"}).json() == cached_by_the_site
        assert list(own_cache) == ["v2:effector-type-labels:fr"]

    def test_an_unknown_language_is_refused(self, directory_site, own_cache):
        assert get_v2({"language": "xx"}).status_code == 422


@pytest.fixture
def every_language_cached(own_cache):
    for key in LABEL_CACHE_KEYS:
        own_cache[key] = {"stale": True}
    return own_cache


class TestEveryWriteClearsEveryLanguage:
    def test_saving_a_label(self, every_language_cached, genders):
        make_label(uuid.uuid4(), genders["neutral"], "S", "pharmacie")

        assert not LABEL_CACHE_KEYS & set(every_language_cached)

    def test_the_clear_all_cache_command(self, every_language_cached):
        from django.core.management import call_command

        call_command("clear_all_cache")

        assert not LABEL_CACHE_KEYS & set(every_language_cached)

    def test_the_create_effector_type_command(self):
        import inspect
        from directory.management.commands import create_effector_type

        assert "sync_clear_effector_type_labels_cache" in inspect.getsource(create_effector_type)
