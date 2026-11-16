"""Cloning an entry carries everything its page and its listing rest on.

The first clone wrote the person, the occupation, the place and the old facets, and
nothing else: a santé mentale entry arrived with no description, no facets, nothing it
manages (so it was not even listed), no area, no porteur, no phone, no opening hours,
no picture and no tags. Each is copied after the Entry exists, past the point of no
rollback, so each failure is a warning naming what was left out, never a failed clone.

Reference data is matched, never created, as effector types already are: what an entry
manages by slug, a tag by name, a place by its kind and code (a commune by its name and
its département's code). A porteur is the local entry the batch cloned it to, or one
already here under the same slug.
"""
import base64

import pytest
import pytest_asyncio
from asgiref.sync import sync_to_async
from neomodel import adb

from addressbook.models import Contact
from api.serializers.clone import execute
from api.types.clone import Resolution

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True),
]

TAG = "e2eCloneRich"
#: A 1x1 PNG: the avatar is a file, copied as bytes.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
ALL_ROLES = ["anonymous", "registered", "staff", "administrator", "superuser"]

_PERSON = 0


def full_entry(**over):
    """A FullEntry payload as the source instance returns it, santé mentale fields included."""
    global _PERSON
    _PERSON += 1
    base = {
        "uid": f"source-{_PERSON}",
        "name": f"Service Riche{_PERSON}",
        "label": f"Service Riche{_PERSON}",
        "slug": f"service-riche{_PERSON}",
        "gender": None,
        "access": "anonymous",
        "effector_type": {"unique_ID": f"{TAG}-UID", "name": "service riche", "slug": f"{TAG}-type-slug"},
        "facility": {"name": "Lieu Riche", "slug": f"{TAG}-fac-{_PERSON}", "label": ""},
        "address": {"street": f"{_PERSON} Rue Riche", "zip": "00000", "city": "Richtown",
                    "building": "", "geographical_complement": "",
                    "longitude": "4.85", "latitude": "45.75", "zoom": 18},
        "payment_methods": [], "third_party_payers": [], "convention": None,
        "memberships": [], "rpps": None, "spoken_languages": [],
    }
    base.update(over)
    return base


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def graph():
    await adb.cypher_query(
        "MATCH (n) WHERE n.uid STARTS WITH $tag OR n.slug STARTS WITH $tag DETACH DELETE n", {"tag": TAG})
    await adb.cypher_query(
        """
        CREATE (c:Commune:AdministrativeTerritorialEntityOfFrance {uid:$tag+'-commune', name_fr:'Richtown',
               slug_fr:'richtown', name_en:'Richtown', slug_en:'richtown', wikidata:$tag+'-Q1'})
        CREATE (dep:DepartmentOfFrance {uid:$tag+'-dept', name:'Richdept', slug:'richdept', code:'R0'})
        CREATE (reg:RegionOfFrance {uid:$tag+'-reg', name:'Richregion', slug:'richregion', code:'R9'})
        CREATE (fr:Country {uid:$tag+'-country', name:'Zedland', slug:'zedland', code:'ZZ'})
        CREATE (c)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dep)
        CREATE (dep)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(reg)
        CREATE (reg)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(fr)
        CREATE (:Entry {uid:$tag+'-org', slug:$tag+'-org', active:true})
        CREATE (:Directory {uid:$tag+'-dir', name:$tag+'-dir'})
        CREATE (:EffectorType {uid:$tag+'-type', unique_ID:$tag+'-UID', name_fr:'service riche',
                               slug_fr:$tag+'-type-slug'})
        CREATE (:Condition {uid:$tag+'-c', slug:$tag+'-cond', name_fr:'Condition riche'})
        CREATE (:Situation {uid:$tag+'-s', slug:$tag+'-sit', name_fr:'Situation riche'})
        CREATE (:Need {uid:$tag+'-n', slug:$tag+'-need', name_fr:'besoin riche'})
        CREATE (:Tag {uid:$tag+'-tag', name:$tag+'-tagname', label:'Étiquette riche', labelShort:'ER'})
        CREATE (:Entry {uid:$tag+'-porteur', slug:$tag+'-porteur-slug', active:true})
        """,
        {"tag": TAG},
    )
    yield {"org": f"{TAG}-org", "dir": f"{TAG}-dir"}
    await adb.cypher_query(
        "MATCH (d:Directory {name:$dir})-[:HAS_ENTRY]->(e:Entry) "
        "OPTIONAL MATCH (e)-[:HAS_EFFECTOR]->(eff:Effector) "
        "OPTIONAL MATCH (e)-[:HAS_FACILITY]->(f:Facility) "
        "OPTIONAL MATCH (e)-[:HAS_SCHEDULE]->(s:Schedule) "
        "DETACH DELETE e, eff, f, s", {"dir": f"{TAG}-dir"})
    await adb.cypher_query(
        "MATCH (n) WHERE n.uid STARTS WITH $tag OR n.slug STARTS WITH $tag "
        "OR n.creator_directory = $tag+'-dir' DETACH DELETE n", {"tag": TAG})


async def _clone(full, graph, **kwargs):
    res = Resolution(source_uid=full["uid"], effector="create", facility="create")
    result = await execute.clone_one(
        full, res, directory_name=graph["dir"], org_uid=graph["org"],
        source_org_entry=None, creator_uid=None, **kwargs,
    )
    assert result.status == "created", result.error
    return result


async def _one(query, **params):
    rows, _ = await adb.cypher_query(query, params)
    return rows


class TestWhatTheEntrySays:
    async def test_its_description_siren_and_every_facet_are_copied(self, graph):
        r = await _clone(full_entry(
            description="Avis de psychiatres, à distance.", siren="266900083",
            age_min=18, age_max=None, care_levels=["secondary"], who_can_contact="professionals",
            access_modes=["teleexpertise"], audiences=["students"], free=True, anonymous_care=True,
            offers=["orientation", "consultation"],
        ), graph)
        rows = await _one(
            "MATCH (e:Entry {uid:$e}) RETURN e.description, e.siren, e.age_min, e.age_max, e.care_levels, "
            "e.who_can_contact, e.access_modes, e.audiences, e.free, e.anonymous_care, e.offers", e=r.entry_uid)
        assert rows[0] == ["Avis de psychiatres, à distance.", "266900083", 18, None, ["secondary"],
                           "professionals", ["teleexpertise"], ["students"], True, True,
                           ["orientation", "consultation"]]
        assert r.warnings == []

    async def test_a_facet_this_instance_does_not_know_is_left_out_and_named(self, graph):
        r = await _clone(full_entry(offers=["massage"], free=True), graph)
        rows = await _one("MATCH (e:Entry {uid:$e}) RETURN e.offers, e.free", e=r.entry_uid)
        assert rows[0] == [None, True]
        assert any("offers" in w for w in r.warnings), r.warnings


class TestWhatItManages:
    async def test_conditions_situations_and_the_need_are_matched_by_slug(self, graph):
        r = await _clone(full_entry(manages=[f"{TAG}-cond", f"{TAG}-sit", f"{TAG}-need"]), graph)
        rows = await _one("MATCH (:Entry {uid:$e})-[:MANAGES]->(t) RETURN t.uid ORDER BY t.uid", e=r.entry_uid)
        assert [row[0] for row in rows] == [f"{TAG}-c", f"{TAG}-n", f"{TAG}-s"]

    async def test_a_slug_missing_here_is_named_and_the_others_kept(self, graph):
        r = await _clone(full_entry(manages=[f"{TAG}-cond", "not-synced-yet"]), graph)
        rows = await _one("MATCH (:Entry {uid:$e})-[:MANAGES]->(t) RETURN t.uid", e=r.entry_uid)
        assert [row[0] for row in rows] == [f"{TAG}-c"]
        assert any("not-synced-yet" in w for w in r.warnings), r.warnings


class TestWhereItAnswers:
    async def test_each_kind_of_place_is_found_by_its_code(self, graph):
        r = await _clone(full_entry(coverage=[
            {"uid": "src-1", "name": "Zedland", "kind": "country", "code": "ZZ", "department": None},
            {"uid": "src-2", "name": "Richregion", "kind": "region", "code": "R9", "department": None},
            {"uid": "src-3", "name": "Richdept", "kind": "department", "code": "R0", "department": None},
            {"uid": "src-4", "name": "Richtown", "kind": "commune", "code": None, "department": "R0"},
        ]), graph)
        rows = await _one("MATCH (:Entry {uid:$e})-[:COVERS]->(t) RETURN t.uid ORDER BY t.uid", e=r.entry_uid)
        assert [row[0] for row in rows] == [f"{TAG}-commune", f"{TAG}-country", f"{TAG}-dept", f"{TAG}-reg"]
        assert r.warnings == []

    async def test_a_place_missing_here_is_named_and_the_others_kept(self, graph):
        r = await _clone(full_entry(coverage=[
            {"uid": "src-3", "name": "Richdept", "kind": "department", "code": "R0", "department": None},
            {"uid": "src-9", "name": "Nowhere", "kind": "commune", "code": None, "department": "R0"},
        ]), graph)
        rows = await _one("MATCH (:Entry {uid:$e})-[:COVERS]->(t) RETURN t.uid", e=r.entry_uid)
        assert [row[0] for row in rows] == [f"{TAG}-dept"]
        assert any("Nowhere" in w for w in r.warnings), r.warnings


class TestWhoRunsIt:
    async def test_the_porteur_the_batch_cloned_runs_it(self, graph):
        r = await _clone(full_entry(run_by={"uid": "src-porteur", "slug": "elsewhere"}), graph,
                         porteurs={"src-porteur": f"{TAG}-porteur"})
        rows = await _one("MATCH (:Entry {uid:$e})-[:RUN_BY]->(p) RETURN p.uid", e=r.entry_uid)
        assert rows == [[f"{TAG}-porteur"]]

    async def test_a_porteur_already_here_is_found_by_its_slug(self, graph):
        r = await _clone(full_entry(run_by={"uid": "src-other", "slug": f"{TAG}-porteur-slug"}), graph)
        rows = await _one("MATCH (:Entry {uid:$e})-[:RUN_BY]->(p) RETURN p.uid", e=r.entry_uid)
        assert rows == [[f"{TAG}-porteur"]]

    async def test_a_porteur_not_here_is_named(self, graph):
        r = await _clone(full_entry(run_by={"uid": "src-gone", "slug": "gone", "name": "Hôpital absent"}), graph)
        rows = await _one("MATCH (:Entry {uid:$e})-[:RUN_BY]->(p) RETURN p.uid", e=r.entry_uid)
        assert rows == []
        assert any("Hôpital absent" in w for w in r.warnings), r.warnings


class TestHowToReachIt:
    async def test_phones_emails_websites_and_social_networks_keep_who_may_see_them(self, graph):
        r = await _clone(full_entry(
            phones=[{"id": 1, "phone": "0437915290", "type": "W", "roles": ALL_ROLES}],
            emails=[{"id": 2, "email": "accueil@example.org", "roles": ["staff", "administrator", "superuser"]}],
            websites=[{"id": 3, "url": "https://example.org/", "roles": ALL_ROLES}],
            socialnetworks=[{"id": 4, "handle": "", "url": "https://www.facebook.com/example", "type": "F",
                             "roles": ALL_ROLES}],
        ), graph)

        @sync_to_async
        def stored():
            c = Contact.objects.get(neomodel_uid=r.entry_uid)
            role_names = lambda item: sorted(role.name for role in item.roles.all())
            return {
                "phones": [(p.phone, p.type, p.public_visible, role_names(p)) for p in c.phonenumbers.all()],
                "emails": [(e.email, e.public_visible, role_names(e)) for e in c.emails.all()],
                "websites": [(w.url, w.public_visible) for w in c.websites.all()],
                "socials": [(s.type, s.url, s.public_visible) for s in c.socialnetworks.all()],
            }

        got = await stored()
        assert got["phones"] == [("0437915290", "W", True, sorted(ALL_ROLES))]
        # Not shown to the public: the source does not let anonymous readers see it.
        assert got["emails"] == [("accueil@example.org", False, ["administrator", "staff", "superuser"])]
        assert got["websites"] == [("https://example.org/", True)]
        assert got["socials"] == [("F", "https://www.facebook.com/example", True)]


class TestOpeningHours:
    async def test_each_schedule_is_recreated(self, graph):
        week = {str(day): [] for day in range(1, 8)}
        week["1"] = [{"opens": "09:00", "closes": "12:30"}]
        r = await _clone(full_entry(schedules=[
            {"uid": "src-sched", "entry": "source", "channel": "phone", "label": "Permanence",
             "holidays": "closed", "days": week},
        ]), graph)
        rows = await _one(
            "MATCH (:Entry {uid:$e})-[:HAS_SCHEDULE]->(s:Schedule) RETURN s.channel, s.label, s.day_1, s.day_2, "
            "s.uid <> 'src-sched'", e=r.entry_uid)
        assert rows == [["phone", "Permanence", ["09:00-12:30"], [], True]]


class TestPictureAndTags:
    async def test_the_avatar_file_and_who_may_see_it_are_kept(self, graph):
        r = await _clone(full_entry(avatar={"raw": "/media/profile_images/x.png", "access": "staff"}), graph,
                         avatar=("logo.png", PNG))

        @sync_to_async
        def stored():
            c = Contact.objects.get(neomodel_uid=r.entry_uid)
            return bool(c.profile_image), c.avatar_access, c.profile_image.read() if c.profile_image else None

        has_image, access, content = await stored()
        assert (has_image, access, content) == (True, "staff", PNG)

    async def test_a_tag_known_here_is_attached_by_name_and_one_unknown_is_named(self, graph):
        r = await _clone(full_entry(tags=[{"uid": "src-tag", "name": f"{TAG}-tagname"},
                                          {"uid": "src-tag2", "name": "unknown-tag"}]), graph)
        rows = await _one("MATCH (t:Tag)-[:TAGS]->(:Entry {uid:$e}) RETURN t.uid", e=r.entry_uid)
        assert rows == [[f"{TAG}-tag"]]
        assert any("unknown-tag" in w for w in r.warnings), r.warnings


class TestABatch:
    async def test_a_service_cloned_with_its_porteur_is_run_by_it_and_shares_its_facility(self, graph):
        """The service has no premises of its own: its facility is its porteur's, which the
        batch creates once, for the porteur, cloned first whatever the order asked."""
        porteur = full_entry(uid="src-hospital", facility={"uid": "src-fac", "name": "Hôpital", "slug": f"{TAG}-hosp"})
        service = full_entry(uid="src-line", facility={"uid": "src-fac", "name": "Hôpital", "slug": f"{TAG}-hosp"},
                             address=porteur["address"], run_by={"uid": "src-hospital", "slug": "elsewhere"})
        results = await execute.clone_batch(
            [(service, Resolution(source_uid="src-line")), (porteur, Resolution(source_uid="src-hospital"))],
            directory_name=graph["dir"], org_uid=graph["org"], source_org_entry=None, creator_uid=None,
        )
        assert [r.source_uid for r in results] == ["src-line", "src-hospital"]
        assert all(r.status == "created" for r in results), [r.error for r in results]
        line, hospital = results
        assert line.facility_uid == hospital.facility_uid
        rows = await _one("MATCH (:Entry {uid:$e})-[:RUN_BY]->(p) RETURN p.uid", e=line.entry_uid)
        assert rows == [[hospital.entry_uid]]


class TestWhatPreflightAnnounces:
    """Preflight names, before anything is written, what this instance would leave out: the
    superuser can sync the console, or add the porteur to the batch, first."""

    async def test_it_names_what_is_not_here(self, graph):
        full = full_entry(
            manages=[f"{TAG}-cond", "not-synced-yet"],
            coverage=[{"kind": "department", "code": "R0", "name": "Richdept"},
                      {"kind": "commune", "name": "Nowhere", "department": "R0"}],
            run_by={"uid": "src-gone", "slug": "gone", "name": "Hôpital absent"},
            tags=[{"name": f"{TAG}-tagname"}, {"name": "unknown-tag"}],
        )
        missing = " | ".join(await execute.missing_here(full, batch=set()))
        for named in ("not-synced-yet", "Nowhere", "Hôpital absent", "unknown-tag"):
            assert named in missing, missing
        for here in (f"{TAG}-cond", "Richdept", f"{TAG}-tagname"):
            assert here not in missing, missing

    async def test_a_porteur_in_the_batch_is_not_missing(self, graph):
        full = full_entry(run_by={"uid": "src-hospital", "slug": "gone", "name": "Hôpital du lot"})
        assert await execute.missing_here(full, batch={"src-hospital"}) == []


class TestWhereThePictureIsFetched:
    """The avatar path comes from the source's payload: it is fetched from the source's own
    origin only, never from a host the payload names."""

    def test_a_path_is_read_on_the_source(self):
        from api.routers.clone import avatar_url
        assert avatar_url("https://dev.example.org", "/media/profile_images/x.png") == \
            "https://dev.example.org/media/profile_images/x.png"

    def test_an_absolute_url_on_the_source_is_kept(self):
        from api.routers.clone import avatar_url
        assert avatar_url("https://dev.example.org/", "https://dev.example.org/media/x.png") == \
            "https://dev.example.org/media/x.png"

    def test_another_host_is_never_fetched(self):
        from api.routers.clone import avatar_url
        assert avatar_url("https://dev.example.org", "https://evil.example.com/x.png") is None
        assert avatar_url("https://dev.example.org", "//evil.example.com/x.png") is None
        assert avatar_url("https://dev.example.org", None) is None


class TestTheBatchOrder:
    """A service needs its porteur's local uid, so a porteur in the batch is cloned first."""

    def test_porteurs_come_before_the_services_they_run(self):
        batch = [{"uid": "service", "run_by": {"uid": "porteur"}},
                 {"uid": "alone"},
                 {"uid": "porteur", "run_by": {"uid": "grand-porteur"}},
                 {"uid": "grand-porteur"}]
        order = [full["uid"] for full in execute.porteurs_first(batch)]
        assert order.index("grand-porteur") < order.index("porteur") < order.index("service")
        assert sorted(order) == ["alone", "grand-porteur", "porteur", "service"]

    def test_a_porteur_outside_the_batch_changes_nothing(self):
        batch = [{"uid": "a", "run_by": {"uid": "elsewhere"}}, {"uid": "b"}]
        assert [full["uid"] for full in execute.porteurs_first(batch)] == ["a", "b"]
