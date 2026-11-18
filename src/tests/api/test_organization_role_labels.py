"""The /organization-role-labels endpoint, over HTTP.

It answers with the same six-slot structure as /effector-type-labels — uid ->
{S,P} -> {F,M,N} — built by the same function, but for `term_type="officer"`
rather than "name". The association page reads it to render officer categories
in the right gender and number.

Two things make it worth its own file rather than a case in
test_effector_type_labels.py. It is the last caller of the *sync* builder in
directory/views.py, reached through sync_to_async, so it is what stands between
that function and deletion: these tests are the check that the migration did
not change the body. And term_type is the axis it exercises — a Label row of
another term_type must not appear here, which is the mirror of the assertion
the effector-type tests make in the other direction.

Nothing covered this endpoint, or any other route in organization_role.py,
before now.
"""
import uuid

import pytest
from asgiref.sync import sync_to_async

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db]


URL = "/api/v2/organization-role-labels"

LANGUAGE = "fr"
TERM_TYPE = "officer"


@pytest.fixture
def genders(transactional_db):
    """The three GrammaticalGender rows the builder looks up by name."""
    from accounts.models import GrammaticalGender

    codes = {"feminine": "F", "masculine": "M", "neutral": "N"}
    rows = {}
    for name, code in codes.items():
        rows[name], _ = GrammaticalGender.objects.get_or_create(
            name=name,
            defaults={"label": name.capitalize(), "code": code},
        )
        if rows[name].code != code:
            rows[name].code = code
            rows[name].save()
    return rows


@pytest.fixture
def organization_site(transactional_db, site):
    """A Site carrying the Organization the endpoint reads its language from.

    The route fetches Organization by site and 500s without one, so this is a
    precondition rather than something under test.
    """
    from directory.models.core import Directory
    from facility.models import Organization

    directory, _ = Directory.objects.get_or_create(
        name="testdirectory",
        defaults={"display_name": "Test Directory", "site": site},
    )
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


def _make_label(uid, gender, number, label, language=LANGUAGE, term_type=TERM_TYPE):
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


# The tests are async, so every ORM call inside them has to cross to a thread;
# Django refuses sync queries in an async context. The fixtures above run in a
# sync context and can use the ORM directly.
make_label = sync_to_async(_make_label)


@sync_to_async
def read_expected_body():
    """Rebuild the expected response from the Label rows themselves."""
    from directory.models.core import Label

    expected = {}
    for row in Label.objects.filter(term_type=TERM_TYPE, language=LANGUAGE):
        slot = expected.setdefault(
            row.uid.hex,
            {
                "S": {"F": None, "M": None, "N": None},
                "P": {"F": None, "M": None, "N": None},
            },
        )
        for gender in row.gender.all():
            slot[row.grammatical_number][gender.code] = row.label
    return expected


@pytest.fixture
def no_cache(monkeypatch):
    """Serve from the database.

    The sync builder this endpoint calls is not itself cached, but the Django
    cache is process-wide in tests; pinning it keeps a neighbouring test's
    entry from being asserted against these rows.
    """
    from django.core import cache as cache_module

    monkeypatch.setattr(cache_module.cache, "get", lambda key, default=None: default)
    monkeypatch.setattr(
        cache_module.cache, "set", lambda key, value, timeout=None: None
    )


class TestTheResponse:
    async def test_it_answers_200_with_json(
        self, versioned_client, organization_site, genders, no_cache
    ):
        response = await versioned_client.get(URL)

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")

    async def test_an_officer_label_appears_under_its_number_and_gender(
        self, versioned_client, organization_site, genders, no_cache
    ):
        uid = uuid.uuid4()
        await make_label(uid, genders["feminine"], "S", "présidente")
        await make_label(uid, genders["masculine"], "S", "président")
        await make_label(uid, genders["feminine"], "P", "présidentes")

        body = (await versioned_client.get(URL)).json()

        assert body[uid.hex] == {
            "S": {"F": "présidente", "M": "président", "N": None},
            "P": {"F": "présidentes", "M": None, "N": None},
        }

    async def test_unauthored_slots_serialise_as_null(
        self, versioned_client, organization_site, genders, no_cache
    ):
        """Null, not absent: the frontend indexes into these without guarding."""
        uid = uuid.uuid4()
        await make_label(uid, genders["neutral"], "S", "trésorerie")

        raw = (await versioned_client.get(URL)).text
        entry = (await versioned_client.get(URL)).json()[uid.hex]

        assert entry["S"]["F"] is None
        assert set(entry["S"]) == {"F", "M", "N"}
        assert set(entry) == {"S", "P"}
        assert '"F":null' in raw.replace(" ", "")

    async def test_a_name_row_does_not_leak_into_officer_labels(
        self, versioned_client, organization_site, genders, no_cache
    ):
        """The axis this endpoint exists to select on.

        term_type="name" rows are the effector-type catalogue served by
        /effector-type-labels; they must not appear here, and vice versa.
        """
        officer_uid = uuid.uuid4()
        name_uid = uuid.uuid4()
        await make_label(officer_uid, genders["neutral"], "S", "secrétariat")
        await make_label(name_uid, genders["neutral"], "S", "dentiste", term_type="name")

        body = (await versioned_client.get(URL)).json()

        assert officer_uid.hex in body
        assert name_uid.hex not in body

    async def test_keys_are_hex_strings(
        self, versioned_client, organization_site, genders, no_cache
    ):
        uid = uuid.uuid4()
        await make_label(uid, genders["neutral"], "S", "trésorerie")

        body = (await versioned_client.get(URL)).json()

        assert uid.hex in body
        assert all(isinstance(k, str) and "-" not in k for k in body)

    async def test_the_whole_body_matches_the_database(
        self, versioned_client, organization_site, genders, no_cache
    ):
        """One assertion over the entire response, rebuilt from the rows.

        This is the one to keep pointed at the endpoint if its implementation
        moves off the sync builder: it says there is nothing extra, nothing
        missing, and no reshaped nesting.
        """
        first, second = uuid.uuid4(), uuid.uuid4()
        await make_label(first, genders["feminine"], "S", "présidente")
        await make_label(first, genders["feminine"], "P", "présidentes")
        await make_label(second, genders["neutral"], "S", "trésorerie")

        body = (await versioned_client.get(URL)).json()

        assert body == await read_expected_body()

    async def test_an_empty_database_is_an_empty_object(
        self, versioned_client, organization_site, genders, no_cache
    ):
        """No officer rows is `{}` — not null, and not an error."""
        body = (await versioned_client.get(URL)).json()

        assert body == {}

    async def test_another_language_leaves_the_slots_null(
        self, versioned_client, organization_site, genders, no_cache
    ):
        """language fills slots; it does not decide which uids are listed.

        Inherited from the shared builder and relied upon: the uid set is the
        catalogue, so a row authored only in English still yields a uid with
        six nulls rather than vanishing.
        """
        uid = uuid.uuid4()
        await make_label(uid, genders["neutral"], "S", "treasury", language="en")

        body = (await versioned_client.get(URL)).json()

        assert body[uid.hex]["S"]["N"] is None
