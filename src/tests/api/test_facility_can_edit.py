"""GET /facilities/{uid}/can-edit — may this caller change this facility?

The frontend cannot work this out. It knows the signed-in user's role but not
which facilities that user is connected to, so without this endpoint it can
only ask "is anybody signed in?" and offers the editing controls to every
visitor with an account — including staff with no connection to the facility,
who are then refused by the server when they try to save.

What these tests pin down is the *equivalence*: the answer has to be the same
one a PUT to the facility would get. Button and server can never disagree, so
whoever is told "yes" can actually save, and nobody is offered a control that
will be refused.

Three things make that equivalence easy to break, and each has a test here:

  * the question is asked with `method="PUT"`. A GET answering "may I edit?"
    judged as a GET checks *read* access and answers yes to everyone — the
    whole point of the endpoint lost, silently, with a 200 and a cheerful
    `{"can_edit": true}`.
  * it asks `may_authorize_api`, which returns a boolean, not `authorize_api`,
    which raises 403. Enforcing here would turn "you may not edit" — a normal
    answer — into an error the page has to catch.
  * the users handed to the rule come from `get_facility_users`, so being
    connected to *this* facility is what counts, not holding a role in general.

Authorization itself is not re-tested here; it belongs to may_authorize_api and
the AccessControl table (see CLAUDE.md). These tests assert that this endpoint
asks the right question of it, and reports the answer faithfully.
"""
import pytest
from unittest.mock import AsyncMock, patch


# The uid is only ever passed through to get_facility_users, which is patched
# in every test, so it needs no particular shape.
FACILITY_UID = "d3b07384d9134c1fa1e0d7ab1f1c9e01"

CAN_EDIT_URL = f"/facilities/{FACILITY_UID}/can-edit"


@pytest.fixture
def signed_in():
    """
    Satisfies the JWT dependency only.

    Authorization is left alone, so each test can assert on what the permission
    rule was asked and what the endpoint did with the answer. The JWT
    dependency is resolved by FastAPI before the handler body runs, so without
    this the request is turned away with a 401 and the handler never reached.
    """
    from main import app
    from api.auth import JWT

    app.dependency_overrides[JWT] = lambda: {"sub": "test-user"}
    try:
        yield
    finally:
        app.dependency_overrides.pop(JWT, None)


def rule_answering(allowed, users=None):
    """
    Replaces the facility lookup and the permission rule.

    Returns the two patchers as a tuple so a test can assert on the calls.
    """
    return (
        patch(
            "api.routers.facilities.get_facility_users",
            new_callable=AsyncMock,
            return_value=users if users is not None else [],
        ),
        patch(
            "api.routers.facilities.may_authorize_api",
            new_callable=AsyncMock,
            return_value=allowed,
        ),
    )


# --- The answer reaches the caller -------------------------------------------


async def test_says_yes_when_the_rule_allows_it(client, signed_in):
    get_users, rule = rule_answering(True)
    with get_users, rule:
        response = await client.get(CAN_EDIT_URL)

    assert response.status_code == 200
    assert response.json() == {"can_edit": True}


async def test_says_no_when_the_rule_refuses(client, signed_in):
    get_users, rule = rule_answering(False)
    with get_users, rule:
        response = await client.get(CAN_EDIT_URL)

    # 200 with can_edit false, *not* a 403: being unable to edit is a normal
    # answer to a normal question. A 403 would make the page treat an ordinary
    # visitor as an error case.
    assert response.status_code == 200
    assert response.json() == {"can_edit": False}


# --- The question asked is the right one -------------------------------------


async def test_asks_whether_the_caller_may_write(client, signed_in):
    """
    The permission checked is PUT's, not the request's own GET.

    Without the method override this endpoint checks read access, which every
    visitor has — so it answers "yes, you may edit" to anonymous visitors while
    looking entirely healthy.
    """
    get_users, rule = rule_answering(True)
    with get_users, rule as may_authorize:
        await client.get(CAN_EDIT_URL)

    assert may_authorize.await_args.kwargs["method"] == "PUT"


async def test_asks_about_the_facilities_endpoint(client, signed_in):
    get_users, rule = rule_answering(True)
    with get_users, rule as may_authorize:
        await client.get(CAN_EDIT_URL)

    assert may_authorize.await_args.args[0] == "facilities_v2"


async def test_hands_the_rule_the_people_answerable_for_this_facility(client, signed_in):
    """
    Connection to *this* facility is what the rule weighs.

    A staff user holds create rights across the site, so judging them on their
    role alone would let any of them edit any facility. The object-level list
    from get_facility_users is what stops that, and it has to reach the rule.
    """
    answerable = [object(), object()]
    get_users, rule = rule_answering(False, users=answerable)
    with get_users as lookup, rule as may_authorize:
        await client.get(CAN_EDIT_URL)

    lookup.assert_awaited_once_with(FACILITY_UID)
    assert may_authorize.await_args.args[3] is answerable


# --- Asking is not enforcing -------------------------------------------------


async def test_a_refusal_is_an_answer_not_an_error(client, signed_in):
    """
    The endpoint must ask may_authorize_api, never authorize_api.

    authorize_api raises 403. Used here it would turn every "no" into an
    exception, so the page could not tell "you may not edit" from "the request
    failed" without catching it — and a broken AccessControl table would look
    the same as an ordinary visitor.
    """
    get_users, rule = rule_answering(False)
    with get_users, rule, patch(
        "api.routers.facilities.authorize_api",
        new_callable=AsyncMock,
        side_effect=AssertionError("can-edit must ask, not enforce"),
    ):
        response = await client.get(CAN_EDIT_URL)

    assert response.status_code == 200


# --- Who is asking -----------------------------------------------------------


async def test_an_anonymous_visitor_is_turned_away(client):
    """
    No JWT override here, so the dependency runs for real.

    A signed-out visitor never sees editing controls, so the page has no reason
    to ask on their behalf — and the endpoint must not answer as though
    somebody were signed in.
    """
    get_users, rule = rule_answering(True)
    with get_users, rule:
        response = await client.get(CAN_EDIT_URL)

    assert response.status_code == 401


async def test_a_missing_facility_is_reported_as_missing(client, signed_in):
    """
    get_facility_users raises 404 for a facility that is not there, and that
    has to reach the caller rather than being flattened into can_edit false —
    a wrong uid is a bug in the page, not a permission decision.
    """
    from fastapi import HTTPException

    with patch(
        "api.routers.facilities.get_facility_users",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=404, detail="Facility not found"),
    ):
        response = await client.get(CAN_EDIT_URL)

    assert response.status_code == 404
