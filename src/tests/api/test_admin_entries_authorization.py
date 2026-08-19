"""Who may read /admin/entries — the gate, before the payload.

This endpoint answers with every entry in the directory including the inactive
ones, each carrying who created it, who owns it, when it was created and why it
was deactivated. That is an audit view of the directory's people, and the roles
allowed to see it are hard-coded in the router rather than read from the
AccessControl table.

That is a deliberate departure from every other endpoint here, and these tests
are the reason it is safe: the table is data, so a row granting `staff` read
access is one careless edit or one bad migration away, with no code review and
no failing test. A frozenset in the router cannot be changed without changing
code, and the `staff` case below fails the moment someone widens it.

Written before the endpoint, so they start red — a gate that has never been
seen to refuse anybody is not a gate.
"""
import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db]


URL = "/api/v2/admin/entries"

# What the router hard-codes. Duplicated here on purpose: if someone widens
# ADMIN_ROLES, this list does not follow automatically and the tests below
# fail, which is the whole point.
ALLOWED = ["administrator", "superuser"]
REFUSED = ["staff", "registered", "owner", None]


@pytest.fixture
def mock_role(monkeypatch):
    """Patch the role lookup where the router imports it.

    Not the `mock_neo4j_role` fixture from conftest: that patches
    `api.auth.get_neo4j_role`, the copy `authorize_api` uses. This endpoint
    deliberately does not go through authorize_api, so it holds its own
    reference and the conftest fixture would leave the real lookup in place —
    a test that passed while asserting nothing.
    """
    from contextlib import contextmanager
    from unittest.mock import AsyncMock

    @contextmanager
    def _mock(role_name: str | None):
        import api.routers.admin_entries as router_module

        monkeypatch.setattr(
            router_module,
            "get_neo4j_role",
            AsyncMock(return_value=role_name),
        )
        yield

    return _mock


@pytest.fixture
def mock_site(monkeypatch, site):
    """Patch the Site lookup where the router imports it.

    Same reasoning as mock_role: the router holds its own reference, so
    patching api.auth's copy would leave the real lookup in place and every
    request would 403 on a missing Site rather than on the role — the tests
    would pass while asserting nothing about the gate.
    """
    from contextlib import contextmanager
    from unittest.mock import AsyncMock

    @contextmanager
    def _mock():
        import api.routers.admin_entries as router_module

        monkeypatch.setattr(
            router_module,
            "get_site_from_request",
            AsyncMock(return_value=site),
        )
        yield

    return _mock


@pytest.fixture
def stub_payload(monkeypatch):
    """Answer the route body without touching Neo4j.

    These tests are about the gate, not the payload — which has its own file.
    `adb` is a process-global connection whose sockets are bound to one event
    loop, so letting an authorization test reach the graph makes it fail on
    loop reuse rather than on anything it asserts.
    """
    from unittest.mock import AsyncMock

    import api.routers.admin_entries as router_module

    monkeypatch.setattr(
        router_module, "get_admin_entries", AsyncMock(return_value=[])
    )


@pytest.fixture
def directory_for_site(transactional_db, site):
    """A Directory the router can resolve for the test site.

    Only the 200-expecting tests need it: a refusal happens in the dependency,
    before the route body ever looks for a directory.
    """
    from directory.models.core import Directory

    directory, _ = Directory.objects.get_or_create(
        name="testdirectory",
        defaults={"display_name": "Test Directory", "site": site},
    )
    if directory.site_id != site.id:
        directory.site = site
        directory.save()
    return directory


@pytest.fixture
def any_jwt():
    """A signed-in caller. Which user they are is the role mock's business."""
    return {
        "email": "someone@example.com",
        "providerAccountId": "some-sub",
        "sub": "some-sub",
        "name": "Someone",
    }


class TestOnlyAdminsMayRead:
    @pytest.mark.parametrize("role", ALLOWED)
    async def test_an_admin_role_is_let_in(
        self, versioned_client, patch_jwt, mock_role, any_jwt, mock_site,
        directory_for_site, stub_payload, role
    ):
        with patch_jwt(any_jwt), mock_role(role), mock_site():
            response = await versioned_client.get(URL)

        assert response.status_code == 200, (
            f"{role} should be allowed, got {response.status_code}"
        )

    @pytest.mark.parametrize("role", REFUSED)
    async def test_every_other_role_is_refused(
        self, versioned_client, patch_jwt, mock_role, any_jwt, mock_site, role
    ):
        """staff is the case that matters.

        It has read access to entries_v2 and to plenty else, so it is the role
        somebody would plausibly add to an ACL row for this endpoint "so the
        secretary can check the list". Here that decision has to be made in
        code.
        """
        with patch_jwt(any_jwt), mock_role(role), mock_site():
            response = await versioned_client.get(URL)

        assert response.status_code == 403, (
            f"{role} should be refused, got {response.status_code}"
        )

    async def test_a_caller_with_no_jwt_is_refused(
        self, versioned_client, mock_role, mock_site
    ):
        """No cookie at all — the anonymous visitor."""
        with mock_role(None), mock_site():
            response = await versioned_client.get(URL)

        assert response.status_code in (401, 403)


class TestTheRefusalLeaksNothing:
    """A 403 must not describe what was refused, or carry any entry data."""

    @pytest.mark.parametrize("role", ["staff", "registered", None])
    async def test_no_entry_data_rides_along_with_the_refusal(
        self, versioned_client, patch_jwt, mock_role, any_jwt, mock_site, role
    ):
        with patch_jwt(any_jwt), mock_role(role), mock_site():
            response = await versioned_client.get(URL)

        body = response.text.lower()
        for leaked in ("createdby", "owner", "creator", "deactivation", "entries"):
            assert leaked not in body, (
                f"a refusal to {role} mentioned {leaked!r}: {response.text[:200]}"
            )


class TestSuspensionIsHonoured:
    """A suspended administrator holds the role but must not get in.

    get_neo4j_role returns None for a suspended access — the Access node stays
    active and keeps its role so the dashboard can explain the suspension, but
    every authorization decision reads through that lookup. This endpoint
    inherits the behaviour rather than special-casing it, and this test is what
    says so out loud.
    """

    async def test_a_suspended_admin_gets_no_role_and_is_refused(
        self, versioned_client, patch_jwt, mock_role, any_jwt, mock_site
    ):
        # What _find_user_by_sub yields for a suspended access.
        with patch_jwt(any_jwt), mock_role(None), mock_site():
            response = await versioned_client.get(URL)

        assert response.status_code in (401, 403)


class TestTheAclTableIsNotConsulted:
    """The gate must not depend on AccessControl rows existing or saying yes.

    may_authorize refuses when the Endpoint row is missing, so an endpoint that
    used the table would fail closed here — passing this test for the wrong
    reason. The second case is the real assertion: a table that says "staff may
    read" changes nothing.
    """

    async def test_an_admin_is_let_in_with_no_endpoint_row_at_all(
        self, versioned_client, patch_jwt, mock_role, any_jwt, mock_site,
        directory_for_site, stub_payload,
    ):
        from access.models import Endpoint

        assert not await Endpoint.objects.filter(name="admin_entries_v2").aexists()

        with patch_jwt(any_jwt), mock_role("administrator"), mock_site():
            response = await versioned_client.get(URL)

        assert response.status_code == 200

    async def test_a_permissive_acl_row_does_not_let_staff_in(
        self, versioned_client, patch_jwt, mock_role, any_jwt, mock_site
    ):
        """The scenario the hard-coding exists to survive."""
        from asgiref.sync import sync_to_async

        # access.models.Endpoint, not directory.models.api.Endpoint: two models
        # share the name and AccessControl points at this one.
        from access.models import AccessControl, Endpoint

        @sync_to_async
        def grant_staff_everything():
            from access.models import Role

            endpoint, _ = Endpoint.objects.get_or_create(name="admin_entries_v2")
            staff, _ = Role.objects.get_or_create(name="staff")
            AccessControl.objects.update_or_create(
                endpoint=endpoint,
                role=staff,
                defaults={"permissions": 15},
            )

        await grant_staff_everything()

        with patch_jwt(any_jwt), mock_role("staff"), mock_site():
            response = await versioned_client.get(URL)

        assert response.status_code == 403, (
            "an AccessControl row granting staff full permissions let them in; "
            "the roles for this endpoint are supposed to be hard-coded"
        )
