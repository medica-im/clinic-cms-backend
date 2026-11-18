"""A role travels as its name, not as an object.

`superuser`, `staff`, `administrator`, `registered`, `anonymous` — the name is
the identifier, and the identifier is the only part of a role the frontend can
use. It renders the label from `src/lib/roles.ts` and authorises nothing
client-side, so `id` and `description` are weight on the wire and nothing else.

Why this is a test
------------------
Roles are nested under *every* phone, email, website and social-media record of
every entry. On 2026-08-15 dropping `Role.label` left two Pydantic models still
declaring it required, and the entries endpoint 500'd for any site with contact
data — thousands of validation errors, one per phone per role. The frontend had
never read the field: every consumer already does
`data.roles.map((e) => e.name)`.

A field no client reads can still break the response that carries it. So the
rule is not "keep these fields in step", it is "do not send them".

These tests are deliberately about the *serialised shape* rather than the model
attributes. The last break passed a model-level check — the field really was
gone from `access.Role` — and still 500'd, because the failure was in a
different layer. Asserting on a round-trip is what would have caught it.
"""
import pytest
from pydantic import ValidationError

from api.types import allentry, fullentry, public_facility, socialmedia
from api.types.shared import Roles


# Every roles-bearing model in api.types, discovered rather than listed.
# A hand-written list is wrong the moment somebody adds a type — and it was:
# the first version of this test named "Phone" in four modules, where two of
# them call it PhonePublic and SocialMedia, so those two silently skipped.
def _role_bearing():
    import pkgutil
    import importlib
    from pydantic import BaseModel

    import api.types

    found = []
    for info in pkgutil.iter_modules(api.types.__path__):
        module = importlib.import_module(f"api.types.{info.name}")
        for name, obj in vars(module).items():
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseModel)
                and obj.__module__ == module.__name__
                and "roles" in getattr(obj, "model_fields", {})
            ):
                found.append(pytest.param(obj, id=f"{info.name}.{name}"))
    return found


ROLE_BEARING = _role_bearing()


@pytest.mark.no_db
class TestTheWireFormat:
    def test_a_role_is_a_plain_string(self):
        # The whole point: `roles: ["staff"]`, not `roles: [{"id": 3, ...}]`.
        assert issubclass(Roles, str), (
            "Roles must serialise as a string so a client can compare it to a "
            "name without unwrapping an object."
        )

    def test_every_role_name_is_available(self):
        # `registered` was missing from the enum for a while, so a payload
        # carrying it could not be built at all.
        names = {r.value for r in Roles}
        assert names == {
            "anonymous",
            "registered",
            "staff",
            "administrator",
            "superuser",
        }, f"the Roles enum does not match the Role table: {sorted(names)}"

    def test_at_least_one_type_carries_roles(self):
        # If discovery finds nothing the parametrised test below passes
        # vacuously, which is the failure mode of every clever test collector.
        assert ROLE_BEARING, "no roles-bearing type found in api.types"

    @pytest.mark.parametrize("model", ROLE_BEARING)
    def test_role_carrying_types_use_bare_names(self, model):
        # The contract: roles travel as names. An object-shaped annotation
        # fails here, whatever the model is called.
        annotation = str(model.model_fields["roles"].annotation)
        assert "Roles" in annotation, (
            f"{model.__module__}.{model.__name__}.roles is {annotation}; it "
            "should be list[Roles] — a list of names, not of role objects."
        )

    def test_an_object_shaped_role_is_rejected(self):
        # Guards the direction of the change: if somebody restores the object,
        # this stops passing quietly.
        from api.types.phones import Phone

        with pytest.raises(ValidationError):
            Phone.model_validate(
                {
                    "id": 1,
                    "type": "landline",
                    "phone": "0102030405",
                    "roles": [{"id": 3, "name": "staff", "description": "..."}],
                }
            )

    def test_a_name_shaped_role_is_accepted(self):
        from api.types.phones import Phone

        phone = Phone.model_validate(
            {
                "id": 1,
                "type": "landline",
                "phone": "0102030405",
                "roles": ["staff", "superuser"],
            }
        )
        # Serialising it back gives plain strings, which is what the frontend's
        # `.map((e) => e.name)` was working around.
        assert phone.model_dump()["roles"] == ["staff", "superuser"]
