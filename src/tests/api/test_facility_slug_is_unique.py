"""A facility's slug addresses it within its organization, so no two of an
organization's facilities may share one.

Facilities are served at /sites/{slug} and fetched by
/api/v2/public/facilities/{slug}, whose Cypher is scoped to the requesting
site's directory and whose caller takes `rows[0]`. Two facilities of the *same*
organization sharing a slug therefore make one unreachable: whichever the graph
returns first answers for both.

Scoped per organization, not globally. "cabinet-medical" and "pharmacie" are
ordinary names and two unrelated organizations are entitled to one each — a
global constraint would refuse the second for no reason, and the endpoint would
never have confused them anyway since it filters by directory. On the
development graph the difference is stark: twenty slugs are shared across all
303 facilities, but only four of those are genuine clashes within one
organization — among them "cabinet-infirmier", held three times by a single
organization.

Nothing prevented it:

  * create_facility assigns `slug=f.slug` without looking;
  * update_facility assigns `node.slug=f.slug` without looking.

A neomodel `unique_index=True` cannot express this: it is global, and would
forbid the legitimate case above. The constraint therefore lives in the two
write paths, which is also where a caller can be told about it — a 409 naming
the facility that already holds the slug.
"""

import ast
import inspect

import pytest

import api.serializers.facility as facility_serializers


# The guard itself lives in a helper both writers call, so "does this write
# path check?" is answered by the writer *plus* whatever it delegates to.
GUARD = "assert_slug_is_free"


def _source(func) -> str:
    """The function's own source, followed by the guard's if it calls it.

    A check factored into a helper is still a check. Reading only the writer
    would demand the Cypher be inlined twice, which is exactly what a shared
    helper is for.
    """
    text = inspect.getsource(func)
    if GUARD in text:
        text += "\n" + inspect.getsource(getattr(facility_serializers, GUARD))
    return text


def _tree(func) -> ast.AST:
    return ast.parse(_source(func).lstrip())


def _queries_slug_within_an_organization(func) -> bool:
    """
    Whether the function asks the graph for a facility with this slug *in the
    same organization* before writing.

    Read from the source rather than by calling it: both writers need a
    Request, a JWT and a live graph, none of which this assertion is about.
    What matters is that the lookup happens and that it is scoped.
    """
    for node in ast.walk(_tree(func)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = " ".join(node.value.lower().split())
            # The alias is the writer's choice (`f.slug`, `other.slug`, ...);
            # what matters is that a facility's slug is matched at all.
            if ".slug" not in text and "slug:" not in text:
                continue
            # PART_OF is how a facility hangs off its Organization or its
            # organization's Entry — see create_facility's own MERGE.
            if "part_of" in text:
                return True
    return False


class TestTheWritePathsCheckWithinTheOrganization:
    def test_creating_a_facility_checks_the_slug(self):
        assert _queries_slug_within_an_organization(
            facility_serializers.create_facility
        ), (
            "create_facility assigns slug=f.slug without asking whether another "
            "facility of the same organization already holds it"
        )

    def test_updating_a_facility_checks_the_slug(self):
        assert _queries_slug_within_an_organization(
            facility_serializers.update_facility
        ), (
            "update_facility assigns node.slug=f.slug without asking whether "
            "another facility of the same organization already holds it"
        )

    @pytest.mark.parametrize(
        "func",
        [facility_serializers.create_facility, facility_serializers.update_facility],
        ids=["create", "update"],
    )
    def test_the_clash_is_reported_as_a_conflict(self, func):
        """
        409, not 400 and not 500: the request is well formed, and the caller
        can fix it by choosing another slug.
        """
        assert "409" in _source(func), (
            f"{func.__name__} does not raise 409 on a duplicate slug"
        )


class TestTheCheckIsScopedRatherThanGlobal:
    """
    Two unrelated organizations may both have a "cabinet-medical". Refusing the
    second would be a regression, and the guard must not be written as a plain
    `MATCH (f:Facility {slug: $slug})`.
    """

    @pytest.mark.parametrize(
        "func",
        [facility_serializers.create_facility, facility_serializers.update_facility],
        ids=["create", "update"],
    )
    def test_the_lookup_is_not_a_bare_global_match(self, func):
        for node in ast.walk(_tree(func)):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            text = " ".join(node.value.lower().split())
            if ".slug" not in text and "slug:" not in text:
                continue
            if "match" not in text:
                continue
            assert "part_of" in text, (
                f"{func.__name__} looks up the slug across every facility; two "
                "organizations are each entitled to a 'cabinet-medical'"
            )


class TestUpdateDoesNotCollideWithItself:
    """
    A facility keeping its own slug through an edit is not a clash. The lookup
    has to exclude the node being written, or saving a facility without
    touching its slug would start failing.
    """

    def test_update_excludes_the_facility_being_edited(self):
        # The writer has to pass the node it is editing...
        call_site = inspect.getsource(facility_serializers.update_facility)
        assert "exclude_uid" in call_site, (
            "update_facility must tell the guard which facility is being "
            "edited, or saving one without touching its slug would fail"
        )
        # ...and the guard has to honour it.
        guard = inspect.getsource(getattr(facility_serializers, GUARD))
        assert "<>" in guard or "not " in guard.lower(), (
            "the guard accepts an exclude_uid but never excludes anything"
        )

    def test_creating_a_facility_excludes_nothing(self):
        """A new facility has no uid yet; there is nothing to exclude."""
        call_site = inspect.getsource(facility_serializers.create_facility)
        assert "exclude_uid" not in call_site
