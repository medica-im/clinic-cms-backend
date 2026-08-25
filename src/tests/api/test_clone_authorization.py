"""Who may clone entries between deployments — the gate, before anything else.

Cloning reads another instance's whole directory: names, addresses, phone
numbers, emails, profile text. It then writes entries into this one. Superuser
on *both* sides, and the role list is hard-coded in the router rather than read
from the AccessControl table.

Same reasoning as test_admin_entries_authorization.py, which this mirrors: the
table is data, so a row granting `administrator` access to a cross-instance
export is one careless edit away, with no code review and no failing test. A
frozenset in the router cannot widen without a diff, and the `administrator`
case below fails the moment someone tries.

`administrator` sits in REFUSED deliberately, unlike admin_entries: an
administrator manages their own directory, and reaching into another
deployment's data is a different power.
"""
import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db]

ALLOWED = ["superuser"]
REFUSED = ["administrator", "staff", "registered", None]

# Every route the module exposes, with the method that reaches it. A new
# endpoint added without a line here is an endpoint nobody proved is gated.
ROUTES = [
    ("GET", "/api/v2/clone/instances", None),
    ("POST", "/api/v2/clone/export-token",
     {"target_origin": "https://example.test", "entry_uids": None}),
    ("GET", "/api/v2/clone/relay/entries?instance=x&token=y", None),
    ("POST", "/api/v2/clone/preflight",
     {"instance": "x", "token": "y", "entry_uids": []}),
    ("POST", "/api/v2/clone/execute",
     {"instance": "x", "token": "y", "resolutions": []}),
]


@pytest.fixture
def mock_role(monkeypatch):
    """Patch the role lookup where the clone router imports it.

    Not api.auth's copy: this router deliberately bypasses authorize_api, so it
    holds its own reference and patching the other one would leave the real
    lookup in place — a test that passes while asserting nothing.
    """
    from contextlib import contextmanager
    from unittest.mock import AsyncMock

    @contextmanager
    def _mock(role_name):
        import api.routers.clone as router_module
        monkeypatch.setattr(router_module, "get_neo4j_role", AsyncMock(return_value=role_name))
        yield

    return _mock


@pytest.fixture
def mock_site(monkeypatch, site):
    from contextlib import contextmanager
    from unittest.mock import AsyncMock

    @contextmanager
    def _mock():
        import api.routers.clone as router_module
        monkeypatch.setattr(router_module, "get_site_from_request", AsyncMock(return_value=site))
        yield

    return _mock


class TestOnlySuperusersMayClone:
    @pytest.mark.parametrize("role", REFUSED)
    @pytest.mark.parametrize("method,url,body", ROUTES)
    async def test_a_lesser_role_is_refused(self, versioned_client, patch_jwt, jwt_superuser,
                                            mock_role, mock_site, role, method, url, body):
        with patch_jwt(jwt_superuser), mock_role(role), mock_site():
            r = await getattr(versioned_client, method.lower())(url, **({"json": body} if body else {}))
        assert r.status_code == 403, (
            f"{method} {url} answered {r.status_code} for role {role!r}; "
            "cloning reads another deployment's contact data"
        )

    @pytest.mark.parametrize("role", ALLOWED)
    @pytest.mark.parametrize("method,url,body", ROUTES)
    async def test_a_superuser_is_let_past_the_gate(self, versioned_client, patch_jwt, jwt_superuser,
                                                   mock_role, mock_site, role, method, url, body):
        """Past the *role* gate, not necessarily to a 200.

        A superuser naming a peer that does not exist gets a 404 from the
        registry, and one naming an unregistered target gets a 403 from it —
        both correct, and neither is the role gate refusing them.

        export-token is therefore excluded from the "not 403" assertion: its
        second gate answers 403 by design, and asserting otherwise would mean
        asserting that an arbitrary origin can be handed a credential for this
        directory. That case has its own test in test_clone_security.py.
        """
        with patch_jwt(jwt_superuser), mock_role(role), mock_site():
            r = await getattr(versioned_client, method.lower())(url, **({"json": body} if body else {}))
        if "export-token" in url:
            # Refused by the peer registry, not by the role gate. Distinguished
            # by the detail, which names the registry.
            assert r.status_code == 403
            assert "peer" in r.text.lower(), (
                "export-token refused a superuser for a reason other than the "
                f"peer registry: {r.text[:200]}"
            )
            return
        assert r.status_code != 403, f"{method} {url} refused a superuser"


class TestAccessControlCannotWidenIt:
    async def test_a_permissive_row_changes_nothing(self, versioned_client, patch_jwt, jwt_superuser,
                                                    mock_role, mock_site, django_db_blocker):
        """The point of hard-coding the roles.

        An AccessControl row granting every permission to `administrator` is
        exactly the change this endpoint must not honour.
        """
        from asgiref.sync import sync_to_async

        def _grant():
            # In a thread: these are synchronous ORM calls and the test body is
            # async, which Django refuses outright.
            from access.models import AccessControl, Endpoint, Role
            with django_db_blocker.unblock():
                endpoint, _ = Endpoint.objects.get_or_create(name="clone")
                role, _ = Role.objects.get_or_create(name="administrator")
                AccessControl.objects.update_or_create(
                    endpoint=endpoint, role=role, defaults={"permissions": 15}
                )

        await sync_to_async(_grant, thread_sensitive=True)()
        with patch_jwt(jwt_superuser), mock_role("administrator"), mock_site():
            r = await versioned_client.get("/api/v2/clone/instances")
        assert r.status_code == 403, (
            "an AccessControl row widened the clone gate; the router must not consult it"
        )
