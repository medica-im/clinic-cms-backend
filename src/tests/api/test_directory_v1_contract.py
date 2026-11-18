"""What /api/v1/directory/ and /api/v1/directory/timestamps answer today.

The frontend reads the first on every page load (the site's directory and
setting) and the e2e helpers read `setting.path` from it. These tests pin the
responses of the Django (DRF) implementation so that a FastAPI /api/v2 version
can be held to the same contract: same status codes, same body, same keys.

Only the `Directory` fixture and BASE change when the endpoint moves.
`current_site` selects the site the way production does, by Host header, since
SITE_ID is not set (backend.settings).
"""

import pytest
from django.test import Client

BASE = "/api/v1/directory"

HOST = "directory.test"


@pytest.fixture
def current_site(site, settings):
    from django.contrib.sites.models import Site

    settings.ALLOWED_HOSTS = ["*"]
    return Site.objects.create(domain=HOST, name="Directory site")


@pytest.fixture
def make_directory(current_site):
    """A directory with its setting and input fields, on `current_site`."""
    from directory.models import Directory, InputField, Setting

    def make(*, site=None, name="annuaire", setting=True, input_field=True, **fields):
        directory = Directory.objects.create(
            name=name,
            display_name=fields.pop("display_name", "Annuaire de santé"),
            presentation=fields.pop("presentation", "Les professionnels de la CPTS."),
            slug=fields.pop("slug", "annuaire"),
            site=site or current_site,
            postal_codes=fields.pop("postal_codes", ["69003", "69007"]),
            department_default=fields.pop("department_default", True),
            commune_default=fields.pop("commune_default", False),
        )
        if input_field:
            InputField.objects.create(
                directory=directory,
                category=True,
                commune=False,
                department=True,
                facility=False,
                geocoder=True,
                organization=False,
                search=True,
                situation=False,
                tag=None,
            )
        if setting:
            Setting.objects.create(
                directory=directory,
                sort_category=fields.pop("sort_category", Setting.ALPHABETICAL),
                display_facility_organization=None,
                display_association=True,
                list_navigation=False,
                type_slug=True,
                path="/annuaire",
            )
        return directory

    return make


def get(path, host=HOST, **extra):
    return Client().get(f"{BASE}{path}", HTTP_HOST=host, **extra)


class TestTheDirectoryOfTheSite:
    def test_the_body_is_the_directory_with_its_input_fields_and_setting(self, make_directory):
        make_directory()

        response = get("/")

        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"
        assert response.json() == {
            "name": "annuaire",
            "display_name": "Annuaire de santé",
            "presentation": "Les professionnels de la CPTS.",
            "slug": "annuaire",
            "postal_codes": ["69003", "69007"],
            "inputField": {
                "category": True,
                "commune": False,
                "department": True,
                "facility": False,
                "geocoder": True,
                "organization": False,
                "search": True,
                "situation": False,
                "tag": None,
            },
            "setting": {
                "sort_category_display": "alphabetical",
                "display_facility_organization": None,
                "display_association": True,
                "list_navigation": False,
                "type_slug": True,
                "path": "/annuaire",
            },
            "department_default": True,
            "commune_default": False,
        }

    def test_the_sort_is_named_not_coded(self, make_directory):
        """`sort_category_display` carries the label, never the stored "IF"."""
        from directory.models import Setting

        make_directory(sort_category=Setting.INVERSE_FREQUENCY)

        assert get("/").json()["setting"]["sort_category_display"] == "inverse_frequency"

    def test_the_slug_is_optional(self, make_directory):
        make_directory(slug=None, postal_codes=None)

        body = get("/").json()

        assert body["slug"] is None
        assert body["postal_codes"] is None

    def test_a_directory_without_setting_or_input_fields_has_them_null(self, make_directory):
        make_directory(setting=False, input_field=False)

        response = get("/")

        assert response.status_code == 200
        assert response.json()["inputField"] is None
        assert response.json()["setting"] is None

    def test_it_is_served_without_a_login(self, make_directory):
        """No permission class: the site's directory is public."""
        make_directory()

        assert get("/").status_code == 200

    def test_the_url_without_its_trailing_slash_redirects_to_it(self, make_directory):
        make_directory()

        response = get("")

        assert response.status_code == 301
        assert response["Location"] == "/api/v1/directory/"

    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    def test_it_only_reads(self, make_directory, method):
        make_directory()

        response = getattr(Client(), method)(f"{BASE}/", HTTP_HOST=HOST)

        assert response.status_code == 405
        assert set(response["Allow"].replace(" ", "").split(",")) == {"GET", "HEAD", "OPTIONS"}


class TestWhichDirectoryAHostGets:
    def test_a_site_with_no_directory_is_a_404_with_a_detail(self, current_site):
        response = get("/")

        assert response.status_code == 404
        assert response.json() == {"detail": "Directory not found."}

    def test_each_site_gets_its_own_directory(self, make_directory, settings):
        from django.contrib.sites.models import Site

        other = Site.objects.create(domain="other.test", name="Other")
        make_directory()
        make_directory(site=other, name="autre", display_name="Autre annuaire", slug="autre")

        assert get("/").json()["name"] == "annuaire"
        assert get("/", host="other.test").json()["name"] == "autre"

    def test_the_directory_the_organization_names_wins_over_the_others(self, make_directory, current_site):
        """Several directories on a site is allowed once the Organization picks one."""
        from facility.models import Organization

        make_directory(name="un", display_name="Un", slug="un")
        chosen = make_directory(name="deux", display_name="Deux", slug="deux")
        Organization.objects.create(name="CPTS", site=current_site, directory=chosen)

        assert get("/").json()["name"] == "deux"


class TestTheTimestamps:
    @pytest.fixture
    def timestamp(self, current_site):
        from directory.models import Endpoint, Timestamp

        def make(endpoint, value, site=None):
            ep, _ = Endpoint.objects.get_or_create(name=endpoint)
            return Timestamp.objects.create(endpoint=ep, site=site or current_site, timestamp=value)

        return make

    def test_a_site_with_none_gets_an_empty_object(self, current_site):
        response = get("/timestamps")

        assert response.status_code == 200
        assert response.json() == {}

    def test_the_body_maps_each_endpoint_to_its_timestamp(self, timestamp):
        timestamp("entries_v2", 1_700_000_000_000)
        timestamp("facilities_v2", 1_700_000_000_123)

        assert get("/timestamps").json() == {
            "entries_v2": 1_700_000_000_000,
            "facilities_v2": 1_700_000_000_123,
        }

    def test_another_sites_timestamps_are_left_out(self, timestamp):
        from django.contrib.sites.models import Site

        other = Site.objects.create(domain="other.test", name="Other")
        timestamp("entries_v2", 1)
        timestamp("entries_v2", 2, site=other)
        timestamp("facilities_v2", 3, site=other)

        assert get("/timestamps").json() == {"entries_v2": 1}

    def test_it_is_served_without_a_login_and_only_reads(self, current_site):
        assert get("/timestamps").status_code == 200
        assert Client().post(f"{BASE}/timestamps", HTTP_HOST=HOST).status_code == 405

    def test_unlike_the_directory_it_has_no_trailing_slash(self, current_site):
        """The two routes disagree: `/` is the directory, `/timestamps/` is a 404."""
        assert get("/timestamps/").status_code == 404
