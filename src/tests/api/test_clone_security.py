"""The security properties of cloning, stated as tests.

Cloning is the only feature that reaches across deployments. It reads a whole
directory's contact data — practitioners' names, addresses, phone numbers,
emails — and writes entries into another instance's graph. The gate is
therefore not one check but several, each closing a different way in:

    the role gate      only a superuser, and only per-instance
    the peer registry  only a deployment this one has agreed to answer
    the token          only the person it was minted for, only that source,
                       only those entries, only for fifteen minutes

test_clone_authorization.py covers the role gate per route, and
test_clone_export_token.py covers the token in isolation. This file covers what
neither does: the routes those files miss, and the cross-instance identity
question — a superuser *here* is not a superuser *there*, and the source must
decide that for itself rather than believe the caller.
"""
import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db]

# Every route the module exposes. Kept complete on purpose: an endpoint added
# without a line here is an endpoint nobody proved is gated.
ALL_ROUTES = [
    ("GET", "/api/v2/clone/instances", None),
    ("POST", "/api/v2/clone/export-token",
     {"target_origin": "https://example.test", "entry_uids": None}),
    ("DELETE", "/api/v2/clone/export-token", None),
    ("GET", "/api/v2/clone/relay/entries?instance=x&token=y", None),
    ("POST", "/api/v2/clone/preflight",
     {"instance": "x", "token": "y", "entry_uids": []}),
    ("POST", "/api/v2/clone/execute",
     {"instance": "x", "token": "y", "resolutions": []}),
]

# Everything short of superuser. `administrator` is here deliberately: they run
# their own directory, and reaching into another deployment's data is a
# different power from managing this one's.
LESSER_ROLES = ["administrator", "staff", "registered", "anonymous", None]


@pytest.fixture
def mock_role(monkeypatch):
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


class TestNoLesserRoleReachesAnything:
    """The whole surface, every role below superuser.

    Parametrised over both so a new route or a new role cannot quietly escape
    the sweep.
    """

    @pytest.mark.parametrize("role", LESSER_ROLES)
    @pytest.mark.parametrize("method,url,body", ALL_ROUTES)
    async def test_it_is_refused(self, versioned_client, patch_jwt, jwt_superuser,
                                 mock_role, mock_site, role, method, url, body):
        with patch_jwt(jwt_superuser), mock_role(role), mock_site():
            r = await getattr(versioned_client, method.lower())(
                url, **({"json": body} if body else {})
            )
        if method == "DELETE":
            # Burning a token needs no role: you can only invalidate one you
            # already hold, and refusing would leave a live credential alive
            # precisely when somebody is trying to dispose of it. Asserted so
            # the exemption is deliberate rather than an oversight.
            assert r.status_code != 500
            return
        assert r.status_code == 403, (
            f"{method} {url} answered {r.status_code} for role {role!r}"
        )


class TestAnAnonymousCallerReachesNothing:
    """No session at all, which is what an internet-facing probe looks like."""

    @pytest.mark.parametrize("method,url,body", ALL_ROUTES)
    async def test_it_is_refused(self, versioned_client, method, url, body):
        r = await getattr(versioned_client, method.lower())(
            url, **({"json": body} if body else {})
        )
        if method == "DELETE":
            assert r.status_code != 500
            return
        assert r.status_code in (401, 403), (
            f"{method} {url} answered {r.status_code} without any credential"
        )


class TestEachInstanceDecidesForItself:
    """A superuser here is not a superuser there.

    The heart of the cross-instance model. `require_superuser` resolves the role
    with `get_neo4j_role(jwt, site)` where `site` comes from the *request host*,
    so the source checks the caller against its own graph and never believes a
    claim carried from elsewhere. Without this, a superuser on any deployment
    could mint a token for every other one.
    """

    async def test_a_superuser_elsewhere_is_refused_here(
        self, versioned_client, patch_jwt, jwt_superuser, mock_role, mock_site
    ):
        # The identity is real and holds superuser on the *calling* instance —
        # jwt_superuser is exactly that. What decides the answer is this
        # instance's own graph, which has never heard of them: role None.
        with patch_jwt(jwt_superuser), mock_role(None), mock_site():
            r = await versioned_client.post(
                "/api/v2/clone/export-token",
                json={"target_origin": "https://example.test", "entry_uids": None},
            )
        assert r.status_code == 403, (
            "an account unknown to this instance was issued an export token; "
            "the source must resolve the role from its own graph"
        )

    async def test_the_role_is_read_from_this_sites_graph(self):
        """Pinned against the source, because the bug would be silent.

        Resolving the role from anything the caller supplies — a header, a
        claim in the token — would still pass every other test in this file.
        """
        import ast
        import inspect

        import api.routers.clone as clone_router

        tree = ast.parse(inspect.getsource(clone_router.require_superuser).lstrip())
        calls = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and (getattr(n.func, "id", None) or getattr(n.func, "attr", None)) == "get_neo4j_role"
        ]
        assert calls, "require_superuser does not consult the graph at all"
        # Second argument is the site, and the site comes from the request.
        assert any(
            getattr(a, "id", None) == "site" for c in calls for a in c.args
        ), "get_neo4j_role is not passed this request's site"


class TestThePeerRegistryIsTheOtherGate:
    """A superuser still cannot point this instance at an arbitrary origin."""

    async def test_an_unregistered_target_is_refused_a_token(
        self, versioned_client, patch_jwt, jwt_superuser, mock_role, mock_site
    ):
        with patch_jwt(jwt_superuser), mock_role("superuser"), mock_site():
            r = await versioned_client.post(
                "/api/v2/clone/export-token",
                json={"target_origin": "https://attacker.example", "entry_uids": None},
            )
        assert r.status_code == 403, (
            "a token was minted for an origin this instance never registered"
        )

    async def test_an_unregistered_peer_cannot_be_read_from(
        self, versioned_client, patch_jwt, jwt_superuser, mock_role, mock_site
    ):
        """The outbound half: a superuser cannot make this server fetch anywhere."""
        with patch_jwt(jwt_superuser), mock_role("superuser"), mock_site():
            r = await versioned_client.post(
                "/api/v2/clone/preflight",
                json={"instance": "not-registered", "token": "x", "entry_uids": []},
            )
        assert r.status_code == 404
