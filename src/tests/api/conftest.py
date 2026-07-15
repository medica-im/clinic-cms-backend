import pytest
from httpx import AsyncClient, ASGITransport

# Real-Neo4j fixtures (neo4j_container / neo4j_connection / neo4j_graph).
# Imported so pytest discovers them; the testcontainers import inside is only
# triggered when a test actually requests the `neo4j_graph` fixture.
from tests.api.conftest_neo4j import (  # noqa: F401
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


@pytest.fixture
def patch_jwt():
    """Returns a context manager that overrides the JWT FastAPI dependency.

    Usage:
        with patch_jwt(jwt_staff):
            response = await client.post(...)
    """
    from contextlib import contextmanager
    from main import app
    from api.auth import JWT

    @contextmanager
    def _patch(jwt_dict: dict | None):
        if jwt_dict is None:
            yield
            return
        app.dependency_overrides[JWT] = lambda: jwt_dict
        try:
            yield
        finally:
            app.dependency_overrides.pop(JWT, None)

    return _patch
