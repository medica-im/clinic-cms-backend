import pytest
from httpx import AsyncClient, ASGITransport

# Real-Neo4j fixtures (neo4j_container / neo4j_connection / neo4j_graph).
# Imported so pytest discovers them; the testcontainers import inside is only
# triggered when a test actually requests the `neo4j_graph` fixture.
from tests.api.conftest_neo4j import (  # noqa: F401
    scratch_database,
    neo4j_container,
    neo4j_bolt_url,
    neo4j_connection,
    neo4j_graph,
)


@pytest.fixture
async def client():
    """Async httpx client wired to the FastAPI app (no server needed)."""
    from main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


class _StripPrefixTransport(ASGITransport):
    """Rewrites /api/v2/x to /x, reproducing what the nginx proxy does.

    nginx *routes* /api/v2/ to this app — `location ^~ /api/v2/ { proxy_pass
    http://uvicorn/; }` — but the trailing slash on that proxy_pass makes it a
    URI-substituting one: nginx replaces the matched location prefix instead of
    appending to it, so FastAPI is handed /users/{uid}/role. That is why the
    routes here are declared bare; verified by hitting uvicorn directly, where
    /users/me is a 401 and /api/v2/users/me a 404, exactly inverting what the
    same two paths return through nginx.

    A test driving the app in-process skips that hop, so without this the
    documented URL — the one the frontend calls and the one the versioning
    convention is about — would 404 on every endpoint. Doing the substitution
    here rather than writing bare paths in the tests keeps the tests stating
    the URL that actually exists from outside.
    """

    PREFIX = "/api/v2"

    async def handle_async_request(self, request):
        path = request.url.path
        if path.startswith(self.PREFIX):
            stripped = path[len(self.PREFIX):] or "/"
            request.url = request.url.copy_with(path=stripped)
            # The ASGI scope is built from the raw path, so rewriting only the
            # URL object would leave the original prefix in place.
            request.extensions = dict(request.extensions)
        return await super().handle_async_request(request)


@pytest.fixture
async def versioned_client():
    """Client that answers on /api/v2, the path callers actually use."""
    from main import app
    transport = _StripPrefixTransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def patch_jwt():
    """Returns a context manager that overrides the JWT FastAPI dependency.

    Usage:
        with patch_jwt(jwt_staff):
            response = await client.post(...)
    """
    from contextlib import contextmanager
    from main import app
    from api.auth import JWT, check_cookie_jwt

    @contextmanager
    def _patch(jwt_dict: dict | None):
        if jwt_dict is None:
            # Both left alone: the mandatory dependency answers 401, and the
            # optional one resolves to no JWT, which is what a signed-out
            # caller actually gets on each kind of endpoint.
            yield
            return
        # Endpoints take one or the other depending on whether a signed-out
        # caller is an error or an answer, so a fixture that overrode only the
        # mandatory one would silently sign the caller out on every endpoint
        # using the optional one.
        app.dependency_overrides[JWT] = lambda: jwt_dict
        app.dependency_overrides[check_cookie_jwt] = lambda: jwt_dict
        try:
            yield
        finally:
            app.dependency_overrides.pop(JWT, None)
            app.dependency_overrides.pop(check_cookie_jwt, None)

    return _patch
