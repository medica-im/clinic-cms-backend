"""A role has a name. What it is *called* is not the backend's business.

`superuser`, `administrator`, `staff`, `registered` and `anonymous` are
identifiers: they are what `AccessControl` rows key on and what
`authorize_api` compares against. Display text is a view concern, and the
frontend already keeps it — in `messages/{fr,en}.json`, behind
`src/lib/roles.ts`, with one component rendering it.

Why this is a test
------------------
Until 2026-08-15 the `Role` model also carried a `label`, translated into
`label_fr` and `label_en`. Nothing served it: no serializer, no endpoint, no
template. It was a second catalogue of the same five strings that only the
Django admin ever displayed, and having no reader it was free to drift — which
it did, in both languages:

======================  ==================  ====================
role                    Postgres label_fr   what the UI showed
======================  ==================  ====================
staff                   Équipe              Équipier
administrator           Administration      Administrateur
anonymous               Visiteur anonyme    Anonyme
======================  ==================  ====================

`label_en` for `administrator` said "Management" where the UI said
"Administrator". Neither was wrong exactly; they were simply two answers, and
nobody could say which one a page was showing without reading both.

The same strings were copied on again into Neo4j `Role` nodes by
`create_neo4j_roles`, a third catalogue with no reader at all — those nodes
have no relationships of any kind, and access is resolved through a `role`
*string property* on `:Access`, never through them.

So this test does not check that a label is correct. It checks that the
backend has stopped holding one, in any of the three places, because a
duplicate with no reader is a duplicate that will drift again.
"""
import pytest

from access.models import Role
from access import neomodels, asyncneomodels


# The fields that were removed. Named individually rather than checked as a
# group so a failure says which one came back.
REMOVED = ["label", "label_fr", "label_en"]


@pytest.mark.no_db
class TestTheDjangoModel:
    def test_role_has_no_label_field(self):
        fields = {f.name for f in Role._meta.get_fields()}
        for name in REMOVED:
            assert name not in fields, (
                f"Role.{name} is back. Role display text belongs to the "
                "frontend (messages/*.json, src/lib/roles.ts); a copy here has "
                "no reader and drifts."
            )

    def test_role_still_has_the_identifier(self):
        # The point is not that the model is emptied — `name` is what every
        # AccessControl row and every authorize_api call keys on.
        fields = {f.name for f in Role._meta.get_fields()}
        assert "name" in fields

    def test_label_is_not_registered_for_translation(self):
        # modeltranslation adds label_fr/label_en from this registration, so
        # leaving it behind would recreate the columns on the next migration.
        from modeltranslation.translator import translator

        opts = translator.get_options_for_model(Role)
        assert "label" not in opts.fields, (
            "label is still registered with modeltranslation; the _fr/_en "
            "columns will come back."
        )


@pytest.mark.no_db
class TestTheGraphNodes:
    """The Neo4j mirror of the same model."""

    @pytest.mark.parametrize("module", [neomodels, asyncneomodels])
    def test_role_node_has_no_label_properties(self, module):
        # Two definitions of the same node, sync and async. The async one was
        # missed the first time these fields were audited, which is why both
        # are named here.
        defined = set(vars(module.Role))
        for name in ["label_fr", "label_en"]:
            assert name not in defined, (
                f"{module.__name__}.Role.{name} is back. These nodes have no "
                "relationships and nothing reads them; access resolves through "
                "the `role` property on :Access."
            )
