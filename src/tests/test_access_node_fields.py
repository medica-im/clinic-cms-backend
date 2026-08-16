"""The Access node carries what an audit needs, in both definitions.

`Access` is defined twice — access/neomodels.py and access/asyncneomodels.py —
and the two describe the same nodes. A property added to one and not the other
exists or not depending on which module a code path imported, which is how
label_fr outlived being dropped everywhere else.

The fields themselves answer three separate questions, and the separation is
the point:

* **Is this the current access?** `active`. One per user per site.
* **When did the previous one end, and who ended it?** `supersededAt` /
  `supersededBy`. A role is never edited in place — changing it deactivates the
  old node and creates a new one — so without these the history knows when a
  role began but not when it stopped.
* **Is the current access usable right now?** `suspendedAt` / `suspendedBy` /
  `suspensionReason`. Deliberately not `active`: a suspended account and a
  superseded one would be indistinguishable, restoring would mean guessing
  which inactive node to revive, and a suspended user could be granted a fresh
  role that arrived silently unsuspended.

`createdByRole` is recorded rather than resolved: an actor demoted next month
still acted as an administrator today.
"""
import pytest

from access import neomodels, asyncneomodels


AUDIT_FIELDS = [
    "createdAt",
    "createdBy",
    "createdByRole",
    "active",
    "supersededAt",
    "supersededBy",
    "suspendedAt",
    "suspendedBy",
    "suspensionReason",
]


@pytest.mark.no_db
@pytest.mark.parametrize("module", [neomodels, asyncneomodels], ids=["sync", "async"])
class TestTheAccessNode:
    @pytest.mark.parametrize("field", AUDIT_FIELDS)
    def test_the_field_exists(self, module, field):
        defined = set(vars(module.Access))
        assert field in defined, (
            f"{module.__name__}.Access has no {field!r}. A role change has to "
            "leave a record of what it replaced and who replaced it."
        )

    def test_suspension_is_not_the_same_flag_as_supersession(self, module):
        # If suspension ever collapses back into `active`, these two stop being
        # separable and the history cannot tell "was demoted" from "was
        # suspended" — the same day, by the same person, reads identically.
        defined = set(vars(module.Access))
        assert "active" in defined and "suspendedAt" in defined


@pytest.mark.no_db
def test_the_two_definitions_agree():
    """Neither copy may carry a property the other lacks."""
    def props(module):
        return {
            name
            for name, value in vars(module.Access).items()
            if not name.startswith("_") and not callable(value)
        }

    sync_only = props(neomodels) - props(asyncneomodels)
    async_only = props(asyncneomodels) - props(neomodels)

    assert not sync_only and not async_only, (
        f"the two Access definitions have drifted — only in sync: {sorted(sync_only)}, "
        f"only in async: {sorted(async_only)}"
    )
