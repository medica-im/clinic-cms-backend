"""When an entry was last modified, and what counts as a modification.

The administrative entries table has a "last modified" column, and the entry
detail page behind it is meant to say *which* part changed and when. Both read
the same thing: a timestamp on every object an owner or an administrator can
edit from /e/{slug}.

The design these tests pin, and the reasoning:

- Each editable object carries its own `updatedAt`, maintained by Django's
  auto_now. Per-object, because the detail page has to distinguish "the phone
  changed on the 12th" from "the website changed on the 14th", and because a
  field the ORM maintains cannot be forgotten by a new write path.

- The entry's own `updatedAt` covers the entry node and its effector — its own
  record, not a rollup of its children.

- "Last modified" for the table is *computed*: the max across the entry and its
  related objects. A denormalised rollup would have to be maintained by every
  writer of every related object, and the moment one path forgets, the column
  lies silently. That is exactly how contactUpdatedAt reached 0 on all 615
  entries in dev while appearing to be wired everywhere.

The awkward case is deletion, and it has its own class below: a deleted row
takes its timestamp with it, so a max() over the survivors can move *backwards*
in time. Nothing else in this design has that property, which is why deleting
has to stamp the entry itself.

Written before the fields exist, so they start red.
"""
import pytest

pytestmark = pytest.mark.django_db


# Everything an owner or admin can edit from the entry page that lives in
# Postgres. The graph-backed ones — tags, memberships, carte_vitale, access,
# the effector's own fields — are stamped separately; see the plan in
# test_entry_graph_timestamps.py when it lands.
EDITABLE_MODELS = [
    # Address was here until the model was deleted: a facility's address lives
    # on the Facility node, so there was no addressbook row left to timestamp.
    "PhoneNumber",
    "Email",
    "Website",
    "SocialNetwork",
    "Appointment",
]

# Profile already carries `created`/`updated` (and a HistoricalRecords trail),
# which is the precedent the fields above follow. It is excluded from the
# parametrised cases only because creating one requires a changed_by user;
# TestProfileAlreadyHadThis keeps it covered.
LEGACY_TIMESTAMPED = ["Profile"]


@pytest.fixture
def contact(transactional_db):
    from addressbook.models import Contact

    return Contact.objects.create(formatted_name="Test Contact")


def make(model_name, contact):
    """One instance of an editable model, with only what it requires."""
    from addressbook import models

    Model = getattr(models, model_name)
    required = {
        "PhoneNumber": dict(phone="0102030405", type="W"),
        "Email": dict(email="test@example.test"),
        "Website": dict(url="https://example.test"),
        "SocialNetwork": dict(url="https://example.test/x"),
        "Appointment": dict(url="https://rdv.example.test"),
    }[model_name]
    return Model.objects.create(contact=contact, **required)


class TestEveryEditableObjectCarriesItsOwnTimestamp:
    """auto_now, not a save() override.

    An override is one more thing a new write path can bypass — and several
    already do: every delete route in api/routers/ calls
    `.filter(...).adelete()`, a queryset delete that never loads the model and
    so never runs its save() or delete().
    """

    @pytest.mark.parametrize("model_name", EDITABLE_MODELS)
    def test_it_has_an_updated_at_field(self, model_name, contact):
        obj = make(model_name, contact)

        assert obj.updatedAt is not None, (
            f"{model_name} has no updatedAt: an edit to it would be invisible "
            "to the administrative table and to the entry detail page"
        )

    @pytest.mark.parametrize("model_name", EDITABLE_MODELS)
    def test_it_moves_when_the_object_is_edited(self, model_name, contact):
        obj = make(model_name, contact)
        before = obj.updatedAt

        obj.save()
        obj.refresh_from_db()

        assert obj.updatedAt > before, (
            f"{model_name}.updatedAt did not move on save"
        )

    @pytest.mark.parametrize("model_name", EDITABLE_MODELS)
    def test_it_is_set_on_creation(self, model_name, contact):
        """A created object is a modification of the entry too.

        Otherwise an entry whose every object was created and never edited
        would report no modification at all.
        """
        from django.utils import timezone

        obj = make(model_name, contact)

        assert (timezone.now() - obj.updatedAt).total_seconds() < 60


class TestProfileAlreadyHadThis:
    """The model the others are modelled on.

    Profile has carried `updated` (auto_now) and a simple_history trail since
    before this work. Named here so the inconsistency is deliberate and
    visible: if the field names are ever unified, this test is the one that
    says which way to go.
    """

    def test_profile_keeps_its_own_updated_field(self):
        from addressbook.models import Profile

        names = {f.name for f in Profile._meta.get_fields()}
        assert "updated" in names
        assert "created" in names


class TestTheEntryTimestampCoversItsOwnRecord:
    """Entry.updatedAt is the entry's own record, not a rollup of its children.

    Kept narrow on purpose. A rollup field has to be written by every path that
    touches any related object; a computed max() cannot fall out of step with
    its sources because it has none of its own.
    """

    def test_the_entry_node_exposes_updated_at(self):
        from directory.models.agraph import Entry

        assert hasattr(Entry, "updatedAt")


class TestTheComputedLastModified:
    """What the admin table's column shows: max() across entry and objects.

    At most 223 entries in production and ~563 related rows in total, so this
    is one query with a prefetch, not a fan-out worth denormalising away.
    """

    def test_it_is_the_most_recent_of_the_related_objects(self, contact):
        from addressbook.models import PhoneNumber, Website
        from api.serializers.admin_entries import last_modified_of

        phone = make("PhoneNumber", contact)
        website = make("Website", contact)
        # Touch the website so it is unambiguously the later of the two.
        website.save()
        website.refresh_from_db()

        assert last_modified_of(contact) == website.updatedAt
        assert last_modified_of(contact) > phone.updatedAt

    def test_it_survives_an_entry_with_no_related_objects(self, contact):
        """A bare entry answers with its own creation stamp, not a crash.

        Originally this expected None. The contact carries its own updatedAt
        now — it has to, so that deleting the last related object still leaves
        a timestamp behind — and a contact that exists has by definition been
        written at least once. That is a truthful answer, not a fabricated one.
        """
        from api.serializers.admin_entries import last_modified_of

        assert last_modified_of(contact) is not None


class TestDeletionIsVisible:
    """The case a computed max() gets wrong on its own.

    Deleting the most recently edited object removes its timestamp, so the max
    over what remains is *older* than before the deletion — the table would
    show the entry getting younger. Deleting therefore has to stamp something
    that survives, which is the entry itself.
    """

    def test_deleting_an_object_does_not_move_the_entry_backwards(self, contact):
        from api.serializers.admin_entries import last_modified_of

        make("PhoneNumber", contact)
        website = make("Website", contact)
        website.save()

        before_deletion = last_modified_of(contact)
        website.delete()
        after_deletion = last_modified_of(contact)

        assert after_deletion >= before_deletion, (
            "deleting the most recent object moved the entry's last-modified "
            "date backwards"
        )

    def test_a_queryset_delete_is_also_visible(self, contact):
        """The form every delete route actually uses.

        api/routers/*.py delete endpoints call `.filter(id=...).adelete()`,
        which never loads the instance — so a model-level delete() override
        would not run. This test fails until the routes fetch the instance or
        the entry is stamped some other way.
        """
        from addressbook.models import Website
        from api.serializers.admin_entries import last_modified_of

        website = make("Website", contact)
        website.save()
        before_deletion = last_modified_of(contact)

        Website.objects.filter(id=website.id).delete()

        assert last_modified_of(contact) >= before_deletion
