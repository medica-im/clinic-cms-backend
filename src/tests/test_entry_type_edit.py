"""Who may change an entry's effector type, and until when.

An entry is (person, occupation, place); a wrong occupation used to need a
hand-written Cypher script. It can now be corrected from the entry page, but
only while the entry is young enough that nobody has come to rely on it:

* a superuser, at any time;
* an administrator, within the organization's administrator window
  (Organization.entry_type_edit_days_administrator, 30 days by default);
* the entry's creator or one of its owners ("connected"), within the
  organization's connected window (entry_type_edit_days_connected, 7 days).

Someone both administrator and connected gets the longer of the two. A window
of 0 means never for that role. An entry with no createdAt -- older data --
cannot be shown to be recent, so only a superuser may change it. Past the
window, the page explains why and offers to recreate the entry instead.
"""

from datetime import datetime, timedelta, timezone

import pytest

from directory.entry_type_edit import type_edit_permission

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
DAY_MS = 24 * 60 * 60 * 1000


def created(days_ago: float) -> int:
    return int((NOW - timedelta(days=days_ago)).timestamp() * 1000)


def permission(role, connected=False, created_at=None, admin_days=30, connected_days=7):
    return type_edit_permission(
        role=role,
        connected=connected,
        created_at_ms=created_at,
        now=NOW,
        admin_days=admin_days,
        connected_days=connected_days,
    )


# --- superuser --------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.parametrize("created_at", [created(1), created(3650), None], ids=["new", "old", "no date"])
def test_a_superuser_may_always_change_the_type(created_at):
    p = permission("superuser", created_at=created_at)

    assert p.allowed and p.reason is None
    assert p.window_days is None and p.deadline is None


# --- administrator ----------------------------------------------------------------


@pytest.mark.no_db
def test_an_administrator_may_within_the_window():
    p = permission("administrator", created_at=created(29))

    assert p.allowed
    assert p.window_days == 30
    assert p.deadline == NOW - timedelta(days=29) + timedelta(days=30)


@pytest.mark.no_db
def test_an_administrator_may_not_once_it_has_passed():
    p = permission("administrator", created_at=created(31))

    assert not p.allowed and p.reason == "expired" and p.window_days == 30


@pytest.mark.no_db
def test_the_last_moment_of_the_window_still_counts():
    p = permission("administrator", created_at=created(30))

    assert p.allowed


@pytest.mark.no_db
def test_the_organization_sets_the_administrator_window():
    assert not permission("administrator", created_at=created(10), admin_days=5).allowed
    assert permission("administrator", created_at=created(50), admin_days=60).allowed


# --- creator or owner -------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.parametrize("role", ["staff", "registered"])
def test_a_creator_or_owner_may_within_their_window(role):
    p = permission(role, connected=True, created_at=created(6))

    assert p.allowed and p.window_days == 7


@pytest.mark.no_db
def test_a_creator_or_owner_may_not_once_it_has_passed():
    p = permission("staff", connected=True, created_at=created(8))

    assert not p.allowed and p.reason == "expired" and p.window_days == 7


@pytest.mark.no_db
def test_an_administrator_who_is_also_connected_gets_the_longer_window():
    assert permission("administrator", connected=True, created_at=created(20)).window_days == 30
    assert permission("administrator", connected=True, created_at=created(20), admin_days=3).window_days == 7


# --- nobody else, never, and no date ----------------------------------------------


@pytest.mark.no_db
@pytest.mark.parametrize("role", ["staff", "registered", "anonymous", None])
def test_someone_unconnected_below_administrator_may_not(role):
    p = permission(role, created_at=created(1))

    assert not p.allowed and p.reason == "not_allowed"


@pytest.mark.no_db
def test_a_window_of_zero_means_never_for_that_role():
    p = permission("administrator", created_at=created(0), admin_days=0)

    assert not p.allowed and p.reason == "not_allowed"


@pytest.mark.no_db
@pytest.mark.parametrize("role, connected", [("administrator", False), ("staff", True)])
def test_an_entry_without_a_creation_date_is_only_for_a_superuser(role, connected):
    p = permission(role, connected=connected, created_at=None)

    assert not p.allowed and p.reason == "no_date"


# --- the organization's settings --------------------------------------------------


@pytest.mark.django_db
def test_a_new_organization_gets_the_default_windows():
    from facility.models import Organization

    org = Organization.objects.create(name="Windows")

    assert (org.entry_type_edit_days_administrator, org.entry_type_edit_days_connected) == (30, 7)
