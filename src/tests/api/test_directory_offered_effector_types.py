"""A directory may limit the categories (effector types) its entries can have.

Entry creation offers every EffectorType, several hundred of them; a directory
like unipa's only ever lists a handful of occupations. Superusers and
administrators may name, per directory, the set of types offered:

    (Directory)-[:OFFERS_EFFECTOR_TYPE]->(EffectorType)

* **Edges, not a property.** MERGE makes it a set; deleting a type drops its
  edge instead of leaving a uid that points at nothing. A distinct name, not
  HAS_EFFECTOR_TYPE: that one says what an entry *is*, and a traversal not
  labelled by Entry would start counting directories.
* **No edge, no limit.** Today's behaviour, and what "remove all" returns to.
  So removing the last offered type — or deleting it — lifts the limit.
* **Refused, except for superusers.** Creation and a change of type are
  refused (409 type_not_offered) outside the set. A superuser may still use any
  type, for a one-off entry; their picker is limited too but can show all.
  It depends on who asks, so it is checked beside the role, not in
  AccessControl.
* **Granular writes.** Add one, remove one, remove all — not "replace with this
  set": two administrators editing at once do not overwrite each other.
* **Only this site's directories**, like the owner switch; that switch stays
  superuser-only while this list is open to administrators.
"""
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

DIRECTORY = "offered-types-dir"
OTHER_SITE_DIRECTORY = "offered-types-elsewhere"


@pytest.fixture
async def graph(neo4j_graph):
    """A directory of this site, one of another, and three well-formed types."""
    from neomodel import adb

    uids = {name: uuid.uuid4().hex for name in ("dir", "elsewhere", "nurse", "doctor", "midwife")}
    await adb.cypher_query(
        """
        CREATE (:Directory {uid: $dir, name: $dir_name})
        CREATE (:Directory {uid: $elsewhere, name: $elsewhere_name})
        WITH 1 AS _
        UNWIND [
            {uid: $nurse, name: 'infirmier'},
            {uid: $doctor, name: 'médecin généraliste'},
            {uid: $midwife, name: 'sage-femme'}
        ] AS t
        CREATE (:EffectorType {
            uid: t.uid, name_fr: t.name, label_fr: t.name, slug_fr: t.name,
            synonyms_fr: [], definition_fr: ''
        })
        """,
        {**uids, "dir_name": DIRECTORY, "elsewhere_name": OTHER_SITE_DIRECTORY},
    )
    return uids


@pytest.fixture
async def django_directories(site, transactional_db, graph):
    from django.contrib.sites.models import Site
    from directory.models import Directory

    elsewhere, _ = await Site.objects.aget_or_create(domain="elsewhere.example", defaults={"name": "Elsewhere"})
    await Directory.objects.acreate(name=DIRECTORY, display_name=DIRECTORY, presentation="", site=site)
    await Directory.objects.acreate(
        name=OTHER_SITE_DIRECTORY, display_name=OTHER_SITE_DIRECTORY, presentation="", site=elsewhere,
    )
    return graph


async def offer(*type_uids, directory=DIRECTORY):
    from directory.offered_types import offer as _offer

    for type_uid in type_uids:
        await _offer(directory, type_uid)


@contextmanager
def mock_role(role_name):
    """Patch the role lookup where the directories router imports it."""
    with patch("api.routers.directories.get_neo4j_role", new_callable=AsyncMock, return_value=role_name):
        yield


# ---------------------------------------------------------------------------
# The set
# ---------------------------------------------------------------------------

class TestTheSet:
    async def test_no_edge_means_no_limit(self, graph):
        from directory.offered_types import offered_type_uids

        assert await offered_type_uids(DIRECTORY) is None

    async def test_offering_twice_keeps_one(self, graph):
        from neomodel import adb
        from directory.offered_types import offered_type_uids

        await offer(graph["nurse"], graph["nurse"])
        assert await offered_type_uids(DIRECTORY) == {graph["nurse"]}
        rows, _ = await adb.cypher_query(
            "MATCH (:Directory {name: $name})-[r:OFFERS_EFFECTOR_TYPE]->() RETURN count(r)", {"name": DIRECTORY},
        )
        assert rows[0][0] == 1

    async def test_an_unknown_type_is_not_offered(self, graph):
        from directory.offered_types import offer as _offer, offered_type_uids

        assert await _offer(DIRECTORY, uuid.uuid4().hex) is False
        assert await offered_type_uids(DIRECTORY) is None

    async def test_withdrawing_one_keeps_the_others(self, graph):
        from directory.offered_types import offered_type_uids, withdraw

        await offer(graph["nurse"], graph["doctor"])
        await withdraw(DIRECTORY, graph["nurse"])
        assert await offered_type_uids(DIRECTORY) == {graph["doctor"]}

    async def test_withdrawing_all_lifts_the_limit(self, graph):
        from directory.offered_types import offered_type_uids, withdraw_all

        await offer(graph["nurse"], graph["doctor"])
        await withdraw_all(DIRECTORY)
        assert await offered_type_uids(DIRECTORY) is None

    async def test_a_deleted_type_leaves_the_set(self, graph):
        from neomodel import adb
        from directory.offered_types import offered_type_uids

        await offer(graph["nurse"], graph["doctor"])
        await adb.cypher_query("MATCH (t:EffectorType {uid: $uid}) DETACH DELETE t", {"uid": graph["nurse"]})
        assert await offered_type_uids(DIRECTORY) == {graph["doctor"]}

    async def test_the_set_belongs_to_one_directory(self, graph):
        from directory.offered_types import offered_type_uids

        await offer(graph["nurse"])
        assert await offered_type_uids(OTHER_SITE_DIRECTORY) is None


# ---------------------------------------------------------------------------
# The rule: refused outside the set, except for superusers
# ---------------------------------------------------------------------------

class TestTheRule:
    @pytest.mark.parametrize("role", ["administrator", "staff", "registered", None])
    async def test_a_type_outside_the_set_is_refused(self, graph, role):
        from directory.offered_types import TypeNotOffered, check_type_offered

        await offer(graph["nurse"])
        with pytest.raises(TypeNotOffered):
            await check_type_offered(DIRECTORY, graph["doctor"], role)

    async def test_a_type_in_the_set_passes(self, graph):
        from directory.offered_types import check_type_offered

        await offer(graph["nurse"])
        await check_type_offered(DIRECTORY, graph["nurse"], "staff")

    async def test_a_superuser_may_use_any_type(self, graph):
        from directory.offered_types import check_type_offered

        await offer(graph["nurse"])
        await check_type_offered(DIRECTORY, graph["doctor"], "superuser")

    async def test_without_a_set_every_type_passes(self, graph):
        from directory.offered_types import check_type_offered

        await check_type_offered(DIRECTORY, graph["doctor"], "staff")


class Reached(Exception):
    """Raised by the first lookup after the check: creation got past it."""


@contextmanager
def creation(role):
    """create_entry with everything before its first node lookup stubbed."""
    with (
        patch("api.serializers.entries.validate_access", new_callable=AsyncMock),
        patch("api.serializers.entries.get_site_from_request", new_callable=AsyncMock),
        patch("api.serializers.entries.get_neo4j_role", new_callable=AsyncMock, return_value=role),
        patch(
            "api.serializers.entries.get_directory_from_hostname",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(name=DIRECTORY),
        ),
        patch("api.serializers.entries.AsyncDirectory", MagicMock(nodes=MagicMock(get=AsyncMock(side_effect=Reached)))),
    ):
        yield


def entry_post(type_uid):
    from api.types.entry import EntryPost

    return EntryPost(effector="p" * 32, effector_type=type_uid, facility="f" * 32, memberships=None)


def request():
    return SimpleNamespace(url=SimpleNamespace(hostname="testserver"))


class TestCreation:
    @pytest.mark.parametrize("role", ["administrator", "staff"])
    async def test_refuses_a_type_outside_the_set(self, graph, role):
        from api.serializers.entries import create_entry

        await offer(graph["nurse"])
        with creation(role), pytest.raises(HTTPException) as refused:
            await create_entry(entry_post(graph["doctor"]), request(), {"sub": "x"})
        assert refused.value.status_code == 409
        assert refused.value.detail["code"] == "type_not_offered"

    async def test_goes_on_with_a_type_in_the_set(self, graph):
        from api.serializers.entries import create_entry

        await offer(graph["nurse"])
        with creation("staff"), pytest.raises(Reached):
            await create_entry(entry_post(graph["nurse"]), request(), {"sub": "x"})

    async def test_goes_on_for_a_superuser(self, graph):
        from api.serializers.entries import create_entry

        await offer(graph["nurse"])
        with creation("superuser"), pytest.raises(Reached):
            await create_entry(entry_post(graph["doctor"]), request(), {"sub": "x"})


class TestTypeChange:
    def context(self, graph, role):
        from directory.entry_type_edit import TypeEditPermission

        return SimpleNamespace(
            uid="e" * 32, slug=None, type_uid=graph["midwife"], effector_uid=None, facility_uid=None,
            created_at_ms=None, caller_uid=None, permission=TypeEditPermission(True, None, None, None),
            role=role, directory=DIRECTORY,
        )

    async def test_refuses_a_type_outside_the_set(self, graph):
        from api.serializers.entry_type import EntryTypeRefused, change_entry_type

        await offer(graph["nurse"])
        with pytest.raises(EntryTypeRefused) as refused:
            await change_entry_type(self.context(graph, "administrator"), graph["doctor"])
        assert refused.value.code == "type_not_offered"

    async def test_a_superuser_gets_past_the_set(self, graph):
        """Stopped later, on the entry this test does not create — not by the set."""
        from api.serializers.entry_type import EntryTypeRefused, change_entry_type

        await offer(graph["nurse"])
        with pytest.raises(Exception) as stopped:
            await change_entry_type(self.context(graph, "superuser"), graph["doctor"])
        assert not (isinstance(stopped.value, EntryTypeRefused) and stopped.value.code == "type_not_offered")

    async def test_the_router_answers_409(self, client, patch_jwt, jwt_administrator, graph):
        from api.serializers.entry_type import EntryTypeRefused

        context = self.context(graph, "administrator")
        with (
            patch_jwt(jwt_administrator),
            patch("api.routers.entry_type.type_edit_context", new_callable=AsyncMock, return_value=context),
            patch(
                "api.routers.entry_type.change_entry_type",
                new_callable=AsyncMock,
                side_effect=EntryTypeRefused("type_not_offered"),
            ),
        ):
            r = await client.put(f"/entries/{'e' * 32}/effector-type", json={"effector_type": graph["doctor"]})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "type_not_offered"


# ---------------------------------------------------------------------------
# The picker
# ---------------------------------------------------------------------------

class TestThePicker:
    async def uids(self, client, query=""):
        r = await client.get(f"/effector-types{query}")
        assert r.status_code == 200
        return {t["uid"] for t in r.json()}

    async def test_without_a_set_the_directory_scope_offers_every_type(self, client, django_directories):
        g = django_directories
        assert await self.uids(client, "?scope=directory") == {g["nurse"], g["doctor"], g["midwife"]}

    async def test_the_directory_scope_offers_the_set(self, client, django_directories):
        g = django_directories
        await offer(g["nurse"], g["doctor"])
        assert await self.uids(client, "?scope=directory") == {g["nurse"], g["doctor"]}

    async def test_without_the_scope_every_type_stays(self, client, django_directories):
        """The categories admin page and the person search keep everything."""
        g = django_directories
        await offer(g["nurse"])
        assert await self.uids(client) == {g["nurse"], g["doctor"], g["midwife"]}


# ---------------------------------------------------------------------------
# The Annuaires page's endpoints
# ---------------------------------------------------------------------------

EDITORS = ["superuser", "administrator"]
REFUSED = ["staff", "registered"]


class TestWhoMayEditIt:
    @pytest.mark.parametrize("role", EDITORS)
    async def test_an_editor_adds_removes_and_clears(self, client, patch_jwt, jwt_superuser, django_directories, role):
        g = django_directories
        url = f"/directories/{g['dir']}/effector-types"
        with patch_jwt(jwt_superuser), mock_role(role):
            r = await client.post(url, json={"effector_type": g["nurse"]})
            assert r.status_code == 200
            assert [t["uid"] for t in r.json()["effector_types"]] == [g["nurse"]]

            r = await client.post(url, json={"effector_type": g["doctor"]})
            assert [t["label"] for t in r.json()["effector_types"]] == ["infirmier", "médecin généraliste"]

            r = await client.delete(f"{url}/{g['nurse']}")
            assert r.status_code == 200
            assert [t["uid"] for t in r.json()["effector_types"]] == [g["doctor"]]

            r = await client.delete(url)
            assert r.status_code == 200
            assert r.json()["effector_types"] == []

    @pytest.mark.parametrize("role", EDITORS)
    async def test_an_editor_lists_the_set(self, client, patch_jwt, jwt_superuser, django_directories, role):
        g = django_directories
        await offer(g["midwife"])
        with patch_jwt(jwt_superuser), mock_role(role):
            r = await client.get("/directories")
        assert r.status_code == 200
        assert [t["uid"] for t in r.json()[0]["effector_types"]] == [g["midwife"]]

    @pytest.mark.parametrize("role", REFUSED)
    async def test_others_are_refused(self, client, patch_jwt, jwt_superuser, django_directories, role):
        from directory.offered_types import offered_type_uids

        g = django_directories
        url = f"/directories/{g['dir']}/effector-types"
        await offer(g["nurse"])
        with patch_jwt(jwt_superuser), mock_role(role):
            assert (await client.get("/directories")).status_code == 403
            assert (await client.post(url, json={"effector_type": g["doctor"]})).status_code == 403
            assert (await client.delete(f"{url}/{g['nurse']}")).status_code == 403
            assert (await client.delete(url)).status_code == 403
        assert await offered_type_uids(DIRECTORY) == {g["nurse"]}

    async def test_anonymous_is_refused(self, client, django_directories):
        g = django_directories
        r = await client.post(f"/directories/{g['dir']}/effector-types", json={"effector_type": g["nurse"]})
        assert r.status_code == 401

    async def test_another_sites_directory_is_not_found(self, client, patch_jwt, jwt_superuser, django_directories):
        from directory.offered_types import offered_type_uids

        g = django_directories
        with patch_jwt(jwt_superuser), mock_role("superuser"):
            r = await client.post(f"/directories/{g['elsewhere']}/effector-types", json={"effector_type": g["nurse"]})
        assert r.status_code == 404
        assert await offered_type_uids(OTHER_SITE_DIRECTORY) is None

    async def test_an_unknown_type_is_unprocessable(self, client, patch_jwt, jwt_superuser, django_directories):
        g = django_directories
        with patch_jwt(jwt_superuser), mock_role("administrator"):
            r = await client.post(f"/directories/{g['dir']}/effector-types", json={"effector_type": uuid.uuid4().hex})
        assert r.status_code == 422

    async def test_the_owner_switch_stays_superuser_only(self, client, patch_jwt, jwt_superuser, django_directories):
        g = django_directories
        with patch_jwt(jwt_superuser), mock_role("administrator"):
            r = await client.patch(f"/directories/{g['dir']}", json={"list_owner_entry": False})
        assert r.status_code == 403
