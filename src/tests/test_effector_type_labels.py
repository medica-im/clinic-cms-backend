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


class TestTheLabelDictionary:
    def test_a_label_lands_under_its_number_and_gender(self, genders):
        from directory.views import get_effector_type_labels

        uid = uuid.uuid4()
        make_label(uid, genders["feminine"], "S", "infirmière")

        dictionary = get_effector_type_labels(LANGUAGE, TERM_TYPE)

        assert dictionary[uid.hex]["S"]["F"] == "infirmière"

    def test_every_slot_is_present_even_when_unauthored(self, genders):
        """The frontend indexes without guarding, so the shape is the contract.

        One authored label must not leave the other five slots missing: it
        leaves them None.
        """
        from directory.views import get_effector_type_labels

        uid = uuid.uuid4()
        make_label(uid, genders["feminine"], "S", "infirmière")

        entry = get_effector_type_labels(LANGUAGE, TERM_TYPE)[uid.hex]

        assert set(entry) == {"S", "P"}
        for number in ("S", "P"):
            assert set(entry[number]) == {"F", "M", "N"}
        assert entry["S"]["M"] is None
        assert entry["P"]["F"] is None

    def test_singular_and_plural_are_kept_apart(self, genders):
        from directory.views import get_effector_type_labels

        uid = uuid.uuid4()
        make_label(uid, genders["masculine"], "S", "infirmier")
        make_label(uid, genders["masculine"], "P", "infirmiers")

        entry = get_effector_type_labels(LANGUAGE, TERM_TYPE)[uid.hex]

        assert entry["S"]["M"] == "infirmier"
        assert entry["P"]["M"] == "infirmiers"

    def test_the_uid_key_is_hex_without_hyphens(self, genders):
        """Neo4j node uids are stored hex, and the frontend keys on that form.

        A UUIDField renders with hyphens under str(); the dictionary must not.
        """
        from directory.views import get_effector_type_labels

        uid = uuid.uuid4()
        make_label(uid, genders["neutral"], "S", "CPTS")

        keys = get_effector_type_labels(LANGUAGE, TERM_TYPE)

        assert uid.hex in keys
        assert str(uid) not in keys
        assert "-" not in uid.hex

    def test_another_language_is_not_mixed_in(self, genders):
        """One dictionary is built per language; rows in another must not leak."""
        from directory.views import get_effector_type_labels

        uid = uuid.uuid4()
        make_label(uid, genders["neutral"], "S", "nurse", language="en")

        dictionary = get_effector_type_labels(LANGUAGE, TERM_TYPE)

        # The uid still keys the dictionary — it comes from the term_type
        # filter, which ignores language — but the English label must not fill
        # the French slot.
        assert dictionary[uid.hex]["S"]["N"] is None

    def test_another_term_type_is_not_listed_at_all(self, genders):
        """Unlike language, term_type decides which uids appear as keys."""
        from directory.views import get_effector_type_labels

        uid = uuid.uuid4()
        make_label(uid, genders["neutral"], "S", "CPTS", term_type="label")

        assert uid.hex not in get_effector_type_labels(LANGUAGE, TERM_TYPE)


class TestTheTTLLookup:
    def test_a_site_with_no_row_falls_back_rather_than_raising(self, site, rf):
        """Pins the behaviour the dead `except TTL.DoesNotExist` implies.

        `.first()` returns None for a site with no TTL row, so the except
        branch that used to sit below it was unreachable and the function
        returns None — which the caller reads as "use the default". That was
        silent until get_ttl gained the warning its async twin already had; the
        return value is the contract either way, and this fails if someone
        makes the lookup raise instead.
        """
        from directory.utils import get_ttl

        request = rf.get("/")
        assert get_ttl("v1:effector_type_labels", request) is None

    def test_a_zero_row_is_returned_as_zero(self, site, rf):
        """0 means "do not cache", and must survive the lookup intact.

        The distinction only matters because the caller has to tell it apart
        from None; see TestZeroReachesTheCache below for the half that used to
        get this wrong.
        """
        from directory.models.api import Endpoint, TTL
        from directory.utils import get_ttl

        endpoint, _ = Endpoint.objects.get_or_create(name="v1:effector_type_labels")
        TTL.objects.update_or_create(
            endpoint=endpoint, site=site, defaults={"ttl": 0}
        )

        request = rf.get("/")
        assert get_ttl("v1:effector_type_labels", request) == 0


class TestZeroReachesTheCache:
    """A TTL of 0 must arrive at cache.set as 0, not as the default.

    The endpoint read `get_ttl(...) or TTL`, and 0 is falsy in Python: a row
    saying "never cache this" was silently rewritten to 60 seconds. The async
    call sites already routed through resolve_ttl for exactly this reason
    (test_cache_ttl.TestZeroIsNotMissing pins the helper itself); this one was
    the last holdout, and nothing asserted on what the view actually passed
    down.

    So this test watches the boundary — the timeout handed to cache.set —
    rather than the helper, because that is where the bug was visible.
    """

    def test_a_zero_ttl_is_not_replaced_by_the_default(self, site, genders, rf, monkeypatch):
        from directory.models.api import Endpoint, TTL
        from directory import views

        endpoint, _ = Endpoint.objects.get_or_create(name="v1:effector_type_labels")
        TTL.objects.update_or_create(
            endpoint=endpoint, site=site, defaults={"ttl": 0}
        )

        recorded = {}

        def fake_set(key, value, timeout=None):
            recorded["timeout"] = timeout

        monkeypatch.setattr(views.cache, "get", lambda key: None)
        monkeypatch.setattr(views.cache, "set", fake_set)
        # The view resolves the language through the Directory's Organization;
        # this test is about the timeout, so the graph walk is stubbed out.
        monkeypatch.setattr(
            views, "get_directory", lambda request: _FakeDirectory(site)
        )
        monkeypatch.setattr(views, "sync_set_timestamp", lambda endpoint, site: None)

        # DRF sets self.request during dispatch; calling get() directly means
        # setting it here, since the view reads it for the directory lookup.
        view = views.EffectorTypeLabel()
        request = rf.get("/")
        view.request = request
        view.get(request)

        assert recorded["timeout"] == 0

    def test_an_absent_row_still_falls_back_to_the_default(self, site, genders, rf, monkeypatch):
        """The other half: None must still become the module default."""
        from directory import views

        recorded = {}

        def fake_set(key, value, timeout=None):
            recorded["timeout"] = timeout

        monkeypatch.setattr(views.cache, "get", lambda key: None)
        monkeypatch.setattr(views.cache, "set", fake_set)
        monkeypatch.setattr(
            views, "get_directory", lambda request: _FakeDirectory(site)
        )
        monkeypatch.setattr(views, "sync_set_timestamp", lambda endpoint, site: None)

        # DRF sets self.request during dispatch; calling get() directly means
        # setting it here, since the view reads it for the directory lookup.
        view = views.EffectorTypeLabel()
        request = rf.get("/")
        view.request = request
        view.get(request)

        assert recorded["timeout"] == views.TTL


class _FakeOrganization:
    language = LANGUAGE


class _FakeSite:
    def __init__(self, site):
        self.organization = _FakeOrganization()
        self._site = site


class _FakeDirectory:
    """Stands in for the Directory → Site → Organization walk the view makes."""

    def __init__(self, site):
        self.site = _FakeSite(site)


# ---------------------------------------------------------------------------
# The JSON response
# ---------------------------------------------------------------------------
#
# Everything above tests Python objects. These tests read the serialised body a
# client actually receives, because that is the contract — and because the
# builder and the response can diverge: None has to arrive as null, uid keys
# have to survive as strings, and a caching layer sits between the two.
#
# The v1 Django endpoint is being replaced by a v2 FastAPI router, and the
# whole point of the move is that the body does not change. So these tests are
# written against an `api` fixture rather than a URL, and parametrised over
# every implementation that claims to serve this resource: whatever passes here
# is answering identically. When v1 is deleted, its entry in IMPLEMENTATIONS
# goes with it and the assertions stay exactly as they are.

V1_URL = "/api/v1/directory/effector_type_labels/"
# The v2 route that replaced v1. Both are listed while v1 survives, so any
# divergence between them fails as a divergence.
V2_URL = "/api/v2/effector-type-labels"

IMPLEMENTATIONS = ["v1", "v2"]


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
    from directory import views

    monkeypatch.setattr(views.cache, "get", lambda key: None)
    monkeypatch.setattr(views.cache, "set", lambda key, value, timeout=None: None)


class _Response:
    """The two clients' responses, reduced to what these tests assert on."""

    def __init__(self, status_code, content_type, content):
        self.status_code = status_code
        self.content_type = content_type
        self.content = content

    def json(self):
        import json

        return json.loads(self.content)


@pytest.fixture(params=IMPLEMENTATIONS)
def api(request, directory_site, no_cache, genders):
    """Fetches the label resource from one implementation.

    Parametrised, so every test below runs once per implementation and any
    difference between them fails as a difference — which is the only thing
    that makes "the JSON response remains the same" a testable claim rather
    than a hope.
    """
    if request.param == "v1":
        django_client = request.getfixturevalue("client")

        def fetch():
            response = django_client.get(V1_URL)
            return _Response(
                response.status_code, response["Content-Type"], response.content
            )

        return fetch

    # v2: the FastAPI app, driven in-process on the versioned path the
    # frontend calls. Sync wrapper so these tests stay ordinary functions.
    def fetch():
        import asyncio

        async def _get():
            from httpx import AsyncClient
            from tests.api.conftest import _StripPrefixTransport
            from main import app

            transport = _StripPrefixTransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as ac:
                return await ac.get(V2_URL)

        response = asyncio.run(_get())
        return _Response(
            response.status_code,
            response.headers.get("content-type", ""),
            response.content,
        )

    return fetch


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
