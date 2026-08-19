"""Role-restricted contact data must not reach a lower role.

Seven addressbook models carry a `roles` M2M documented as "Roles allowed so
see the related object": Address, PhoneNumber, Email, Website, SocialNetwork,
Profile, Appointment. The enforcement for all of them is one function —
`api.utils.process` — which keeps only the items whose `roles` contain the
viewer's role, driven by a list of attribute names supplied per serializer.

That list is the whole of the protection: a field emitted by a serializer but
absent from it is published unfiltered, whatever its `roles` say, and nothing
in the type system or the ORM notices. It used to be a literal at each call
site, and fullentry.py's read ["phones", "emails", "socialnetworks"] while the
serializer also emitted websites and appointments — so a website restricted to
administrators was served to anonymous callers. Two such websites existed.

Both call sites now pass api.utils.role_bearing_attributes(), derived from the
models themselves, so the next role-bearing field is covered by being
serialised rather than by being remembered.

So these tests seed a *fully populated* entry: every role-bearing attribute
present, each carrying one item per role level. Real entries are never
complete, so a test built on existing data proves only that absent data is
absent. Here, absence of a staff phone from an anonymous payload means the
scrub removed it, because the seed put it there.

Assertions are made on the serialised body, not the dict, so an item that
survives under a different key or nested somewhere unexpected still fails.
"""
import copy
import json

import pytest

pytestmark = pytest.mark.django_db


# The roles a viewer can hold, weakest first. "registered" is included because
# the ACL grants it access to entries_v2; normalize_neo4j_role folds it onto
# "anonymous" before the scrub sees it, which TestRoleNormalisation pins.
VIEWER_ROLES = ["anonymous", "registered", "staff", "administrator", "superuser"]

# Both serializers now pass api.utils.role_bearing_attributes(), derived from
# the models that declare a `roles` M2M. Resolved lazily inside the tests
# because it touches the Django app registry.
#
# `profile` is excluded there on purpose: it is serialised as a plain string,
# not a list of role-bearing items, so `process` cannot filter it item by item.
# It keeps its own test below.
ROLE_BEARING = ["phones", "emails", "socialnetworks", "websites", "appointments"]
NOT_FILTERABLE = ["profile"]


def attributes() -> list[str]:
    """The list both serializers now pass to `process`."""
    from api.utils import role_bearing_attributes

    return role_bearing_attributes()


def item(kind: str, role: str) -> dict:
    """One contact item visible to exactly `role`.

    The value embeds both, so an assertion on the raw body names precisely
    which item leaked rather than reporting a bare string mismatch.
    """
    return {
        "uid": f"{kind}-{role}-uid",
        "value": f"SECRET-{kind}-for-{role}",
        "roles": [role],
    }


def full_entry(access: str = "anonymous") -> dict:
    """An entry with every role-bearing attribute populated at every level.

    Deliberately more complete than any entry in the database: the leak this
    file exists to catch is a field nobody remembered to add to the scrub list,
    and a sparse fixture cannot express that.
    """
    entry = {
        "uid": "entry-uid-001",
        "name": "Maurice Dantec",
        "slug": "maurice-dantec",
        "access": access,
        # Admin-only, popped by process() for everyone below administrator.
        "redeemEmail": "SECRET-redeem@example.test",
        "avatar": {"sm": "/media/a.jpg", "access": "anonymous"},
    }
    for kind in ROLE_BEARING + NOT_FILTERABLE:
        entry[kind] = [item(kind, role) for role in VIEWER_ROLES]
    return entry


def body(entry: dict) -> str:
    """The entry as a client would receive it."""
    return json.dumps(entry, ensure_ascii=False)


class TestPhonesAcrossRoles:
    """The attribute both serializers scrub, and the one with real data behind it."""

    @pytest.mark.parametrize("viewer", VIEWER_ROLES)
    def test_a_viewer_sees_only_their_own_level(self, viewer):
        from api.utils import process

        entry = full_entry()
        process(entry, viewer, attributes())

        kept = [p["value"] for p in entry["phones"]]
        assert kept == [f"SECRET-phones-for-{viewer}"], (
            f"{viewer} should keep exactly their own phone, got {kept}"
        )

    def test_a_staff_phone_is_absent_from_the_anonymous_body(self):
        """The concrete case: mark a phone staff-only, check anonymous cannot read it."""
        from api.utils import process

        entry = full_entry()
        process(entry, "anonymous", attributes())

        assert "SECRET-phones-for-staff" not in body(entry)
        assert "SECRET-phones-for-administrator" not in body(entry)
        assert "SECRET-phones-for-superuser" not in body(entry)

    def test_an_admin_phone_is_absent_from_the_staff_body(self):
        from api.utils import process

        entry = full_entry()
        process(entry, "staff", attributes())

        assert "SECRET-phones-for-administrator" not in body(entry)
        assert "SECRET-phones-for-superuser" not in body(entry)

    def test_the_item_is_present_at_its_own_level(self):
        """Absence proves scrubbing only if presence is possible.

        Without this, every assertion above would pass against a scrub that
        deleted the attribute outright, or a seed that never populated it.
        """
        from api.utils import process

        entry = full_entry()
        process(entry, "staff", attributes())

        assert "SECRET-phones-for-staff" in body(entry)


class TestFullEntryAttributes:
    """/fullentries scrubs three attributes; each must hold the line."""

    @pytest.mark.parametrize("kind", ROLE_BEARING)
    @pytest.mark.parametrize("viewer", ["anonymous", "registered", "staff"])
    def test_higher_role_items_never_reach_a_lower_viewer(self, kind, viewer):
        from api.utils import process

        entry = full_entry()
        process(entry, viewer, attributes())
        serialised = body(entry)

        higher = VIEWER_ROLES[VIEWER_ROLES.index(viewer) + 1:]
        for role in higher:
            assert f"SECRET-{kind}-for-{role}" not in serialised, (
                f"{viewer} received a {kind} restricted to {role}"
            )


class TestRedeemEmail:
    """An email address, admin-only, popped rather than role-filtered."""

    @pytest.mark.parametrize("viewer", ["anonymous", "registered", "staff"])
    def test_it_is_absent_below_administrator(self, viewer):
        from api.utils import process

        entry = full_entry()
        process(entry, viewer, attributes())

        assert "redeemEmail" not in entry
        assert "SECRET-redeem@example.test" not in body(entry)

    @pytest.mark.parametrize("viewer", ["administrator", "superuser"])
    def test_it_survives_for_admins(self, viewer):
        from api.utils import process

        entry = full_entry()
        process(entry, viewer, attributes())

        assert entry["redeemEmail"] == "SECRET-redeem@example.test"


class TestTheDerivedListCoversEveryModel:
    """The attributes that were missed, and the mechanism that stops the next one.

    websites, appointments and profile each carry a `roles` M2M and were absent
    from the literal ["phones", "emails", "socialnetworks"] that fullentry.py
    used to pass, so an administrator-only website was served to anonymous
    callers. The list is now derived from the models themselves.

    If these assertions fail, restricted data is being published again.
    """

    def test_the_derived_list_matches_the_role_bearing_models(self):
        """Every filterable role-bearing model appears, and nothing else."""
        assert attributes() == sorted(ROLE_BEARING)

    @pytest.mark.parametrize("kind", ROLE_BEARING)
    def test_a_restricted_item_does_not_reach_anonymous(self, kind):
        from api.utils import process

        entry = full_entry()
        process(entry, "anonymous", attributes())

        assert f"SECRET-{kind}-for-administrator" not in body(entry), (
            f"{kind} carries a roles field but is not scrubbed: an "
            f"administrator-only {kind} reached an anonymous viewer"
        )


class TestEntryAccessLevel:
    """filter_by_access drops whole entries above the viewer's level."""

    def test_an_administrator_entry_is_hidden_from_anonymous(self):
        from api.utils import filter_by_access

        entries = [full_entry(access="administrator")]
        assert filter_by_access(copy.deepcopy(entries), "anonymous") == []

    def test_an_anonymous_entry_survives_for_everyone(self):
        from api.utils import filter_by_access

        entries = [full_entry(access="anonymous")]
        for viewer in ("anonymous", "staff", "administrator"):
            assert len(filter_by_access(copy.deepcopy(entries), viewer)) == 1


class TestTheCacheIsPerRole:
    """Each role's payload is cached under its own key.

    The scrub is only as good as the key it is stored under: one shared key
    would serve whichever body was built first to everyone afterwards.
    """

    def test_scrub_returns_a_separate_payload_per_role(self):
        from api.utils import scrub

        scrubbed = scrub([full_entry()], attributes())

        assert set(scrubbed) >= {"anonymous", "staff", "administrator", "superuser"}
        anonymous_body = body(scrubbed["anonymous"][0])
        assert "SECRET-phones-for-administrator" not in anonymous_body
        assert "SECRET-phones-for-staff" not in anonymous_body

    def test_one_roles_payload_is_not_shared_with_another(self):
        """Mutating one role's copy must not reach another's.

        scrub deepcopies per role; if it stopped doing so, two roles would hold
        references to one list and a later scrub would empty both.
        """
        from api.utils import scrub

        scrubbed = scrub([full_entry()], attributes())
        scrubbed["administrator"][0]["phones"].clear()

        assert scrubbed["superuser"][0]["phones"], (
            "clearing the administrator payload emptied another role's"
        )

    def test_the_cache_key_separates_roles(self):
        """Two roles must not collide on one key for the same site and path."""
        import asyncio
        from unittest.mock import patch

        from api.utils import generate_cache_key

        class FakeSite:
            domain = "testserver"

        request = type("R", (), {"scope": {"route": type("P", (), {"path": "/entries"})()}})()

        async def keys():
            with patch("api.utils.get_site_from_request", return_value=FakeSite()):
                return [
                    await generate_cache_key("v2", request, role)
                    for role in ("anonymous", "administrator")
                ]

        anonymous_key, administrator_key = asyncio.run(keys())
        assert anonymous_key != administrator_key


class TestRoleNormalisation:
    """`registered` is folded onto `anonymous` before any scrub runs.

    entries_v2 grants `registered` read access, but the cache holds no bucket
    of its own for it. Folding it onto the weakest role is what makes that
    safe; pinning it here means a future fifth bucket has to be scrubbed
    deliberately rather than appearing unfiltered.
    """

    def test_registered_is_treated_as_anonymous(self):
        from api.neo4j_auth import normalize_neo4j_role

        assert normalize_neo4j_role("registered") == "anonymous"

    def test_no_role_is_treated_as_anonymous(self):
        from api.neo4j_auth import normalize_neo4j_role

        assert normalize_neo4j_role(None) == "anonymous"

    def test_a_privileged_role_is_left_alone(self):
        from api.neo4j_auth import normalize_neo4j_role

        for role in ("staff", "administrator", "superuser"):
            assert normalize_neo4j_role(role) == role
