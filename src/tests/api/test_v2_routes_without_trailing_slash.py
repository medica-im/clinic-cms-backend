"""/api/v2 paths have no trailing slash, and the other form is a 404.

Never a redirect: behind nginx, FastAPI builds a slash redirect from the scheme
it sees, so an HTTPS page was sent to http:// and the browser blocked it as
mixed content. A 404 makes a wrong URL fail in tests instead.
"""
from fastapi.routing import APIRoute


def _app():
    from main import app
    return app


def test_no_v2_route_ends_with_a_slash():
    slashed = sorted(
        route.path
        for route in _app().routes
        if isinstance(route, APIRoute) and route.path != "/" and route.path.endswith("/")
    )
    assert slashed == []


def test_slash_redirects_are_off():
    assert _app().router.redirect_slashes is False


async def test_the_slashed_form_is_a_404_not_a_redirect(client):
    response = await client.get("/conventions/")
    assert response.status_code == 404
