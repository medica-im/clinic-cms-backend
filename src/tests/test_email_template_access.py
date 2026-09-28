"""Who may see and who may change an organization's emails.

Seeing -- the template, its preview, the images and their addresses -- is
for administrators and higher, always: they send the invitations and should
know what they say.

Changing them -- saving, going back to the default, uploading, renaming,
deleting an image -- is the organization's choice, stored on the
Organization row (email_template_editor_role): administrators and higher, or
superusers only. Superusers only by default: an email goes out under the
organization's name, and wording it is a decision an organization opts into
delegating, not one it discovers was delegated.

Roles below administrator see nothing, whatever the choice.
"""

import pytest

from facility.models import Organization
from mailer.access import may_edit, may_view


class Org:
    def __init__(self, editor_role):
        self.email_template_editor_role = editor_role


@pytest.mark.parametrize("role", ["administrator", "superuser"])
def test_administrators_and_higher_may_see(role):
    assert may_view(role)


@pytest.mark.parametrize("role", ["staff", "registered", "anonymous", None, "", "owner"])
def test_everyone_below_administrator_sees_nothing(role):
    assert not may_view(role)


def test_by_default_only_superusers_may_change():
    org = Org("superuser")

    assert may_edit("superuser", org)
    assert not may_edit("administrator", org)


def test_an_organization_may_let_its_administrators_change():
    org = Org("administrator")

    assert may_edit("administrator", org)
    assert may_edit("superuser", org)


@pytest.mark.parametrize("editor_role", ["administrator", "superuser"])
@pytest.mark.parametrize("role", ["staff", "registered", None])
def test_below_administrator_no_choice_lets_anyone_change(editor_role, role):
    assert not may_edit(role, Org(editor_role))


def test_an_unknown_stored_choice_lets_nobody_but_superusers_change():
    # A typo in the row fails closed rather than open.
    org = Org("staff")

    assert not may_edit("staff", org)
    assert not may_edit("administrator", org)
    assert may_edit("superuser", org)


@pytest.mark.django_db
def test_a_new_organization_leaves_its_emails_to_superusers():
    org = Organization.objects.create(name="New")

    assert org.email_template_editor_role == "superuser"


def test_the_choice_is_offered_between_administrators_and_superusers_only():
    field = Organization._meta.get_field("email_template_editor_role")

    assert [value for value, _ in field.choices] == ["administrator", "superuser"]
