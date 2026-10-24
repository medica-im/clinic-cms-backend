"""Import an organization, its facilities and its people from an old-stack export.

The export is the JSON written by scripts/vedene/export_workers.py from a
backend on the old main branch, where people were workforce NetworkNodes in
Postgres. This writes them into this backend's model:

- Postgres: the Site, the Directory, the Organization; one Contact per entry
  and per facility (keyed by neomodel_uid), with its phones, emails, websites,
  social networks, profile and avatar; an EntrySlug per old public slug.
- Neo4j: the Directory node, a Facility per old facility (PART_OF the
  organization's Entry), an Effector per person and an Entry per occupation,
  each listed in the directory and MEMBER_OF the organization's Entry.

The organization itself is an ordinary entry, typed maison de santé
pluriprofessionnelle, at the main facility; Organization.neomodel_uid points
at it and the post_save hook links (Directory)-[:OWNED_BY]->(Entry).

Every write is found-or-created by a natural key, so a rerun after a failure
finishes the job and a rerun after success changes nothing:

- Facility: slug, street and zip;
- Effector: RPPS when there is one (the same person may already be listed by
  another directory), else creator_directory and slug_fr;
- Entry: effector, effector type and facility, as get_entries does.

Old occupations map to effector types by OCCUPATION_TYPES, never by guessing:
an unmapped one aborts the run before anything is written. --dry-run stops
after printing the plan.

Run it in the fastapi container: it reuses api helpers, which import fastapi.

    python manage.py import_entries /tmp/vedene/vedene.json \\
        --site dev.msp-vedene.fr --directory vedene --organization msp-vedene \\
        --main-facility pole_sante_vedene --media-dir /tmp/vedene/media \\
        --changed-by jerome@medecinelibre.com \\
        --redirects-out /tmp/vedene/redirects.json [--dry-run]
"""
import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field

from asgiref.sync import sync_to_async
from django.contrib.sites.models import Site
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify
from neomodel import adb

from access.models import Role
from accounts.models import User
from addressbook.models import Contact, Email, PhoneNumber, Profile, SocialNetwork, Website
from api.serializers.entries import ensure_health_worker_label
from api.utils import clear_cache
from directory.entry_shape import entry_shape_problems
from directory.models import Directory, EntrySlug, InputField, Label, Setting
from directory.models.agraph import (
    Appointment as AsyncAppointment,
    Directory as AsyncDirectory,
    Effector as AsyncEffector,
    EffectorType as AsyncEffectorType,
    Entry as AsyncEntry,
    Facility as AsyncFacility,
)
from directory.slug import generate_entry_slugs
from facility.models import Category, LegalEntity, Organization
from nlp.models import City

# Old occupation, or medical specialty when there is one, to the slug_fr of
# the effector type it becomes. Checked against the graph before any write.
OCCUPATION_TYPES = {
    "coordinator": "coordinateur",
    "dentist": "dentiste",
    "dietitian": "dieteticien",
    "Emergency Medicine": "urgentiste",
    "enseignant_apa": "activite-physique-adaptee",
    "general_practitioner": "medecin-generaliste",
    "governing_board": "gerant",
    "medical_secretary": "secretaire-medical",
    "midwife": "sage-femme",
    "nurse": "infirmiere",
    "osteopathic_manual_practitioner": "osteopathe",
    "pediatrician": "pediatre",
    "pharmacist": "pharmacien",
    "physical_therapist": "kinesitherapeute",
    "physician": "medecin",
    "podologue": "pedicure-podologue",
    "psychiatrist": "psychiatre",
    "psychologist": "psychologue",
    "slp": "orthophoniste",
}
ORGANIZATION_TYPE = "maison-de-sante-pluriprofessionnelle"

# Roles rather than occupations: listed after the person's clinical entry, so
# the old public slug goes to the clinical one, and without its billing or
# appointments, which belong to the practice.
SECONDARY = {"governing_board", "coordinator"}

GENDERS = {"feminine": "F", "masculine": "M"}

# A person the old site showed to superusers only is imported inactive.
PUBLIC_ROLE = "anonymous"


@dataclass
class PlannedEntry:
    worker: dict
    type_slug: str
    facility: str
    active: bool
    old_slug: str | None
    secondary: bool = False


@dataclass
class Report:
    created: dict = field(default_factory=lambda: {"facility": 0, "effector": 0, "entry": 0})
    reused: dict = field(default_factory=lambda: {"facility": 0, "effector": 0, "entry": 0})
    dropped: list = field(default_factory=list)
    redirects: dict = field(default_factory=dict)


def name_of(worker: dict) -> str:
    contact = worker["contact"] or {}
    return " ".join((contact.get("formatted_name") or worker["node"]["name"]).split())


def plan_entries(data: dict, main_facility: str) -> tuple[list[PlannedEntry], list[str]]:
    """One planned entry per person, occupation and facility, and the problems
    (unmapped occupations) that must stop the import."""
    planned, problems = [], []
    for worker in data["workers"]:
        # Stable: the old order holds, except that roles go last.
        occupations = sorted(worker["occupations"], key=lambda o: o["name"] in SECONDARY)
        active = PUBLIC_ROLE in worker["visible_to"]
        old_slug = worker["slug"]
        for occupation in occupations:
            key = (occupation["specialty"] or {}).get("name") or occupation["name"]
            type_slug = OCCUPATION_TYPES.get(key)
            if type_slug is None:
                problems.append(f"{name_of(worker)}: no effector type for occupation '{key}'")
                continue
            facilities = sorted({f for e in occupation["edges"] for f in e["facilities"]})
            for facility in facilities or [main_facility]:
                planned.append(PlannedEntry(
                    worker, type_slug, facility, active, old_slug,
                    secondary=occupation["name"] in SECONDARY,
                ))
                old_slug = None
    return planned, problems


async def rows(query: str, **params) -> list:
    result, _ = await adb.cypher_query(query, params)
    return result


class Command(BaseCommand):
    help = "Import an organization, its facilities and its people from an old-stack export"

    def add_arguments(self, parser):
        parser.add_argument("json_path")
        parser.add_argument("--site", required=True, help="domain of the Site, e.g. msp-vedene.fr")
        parser.add_argument("--directory", required=True, help="name of the Directory, e.g. vedene")
        parser.add_argument("--organization", required=True, help="name of the Organization, e.g. msp-vedene")
        parser.add_argument("--main-facility", required=True, help="old name of the organization's own facility")
        parser.add_argument("--media-dir", help="old MEDIA_ROOT, for avatars")
        parser.add_argument("--changed-by", help="email of the user recorded as the profiles' author")
        parser.add_argument("--redirects-out", help="write old path -> new path as JSON here")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        with open(options["json_path"]) as f:
            data = json.load(f)
        self.options = options
        self.report = Report()
        asyncio.run(self.run(data))

    def say(self, message, style=None):
        self.stdout.write(style(message) if style else message)

    # --- preflight ---------------------------------------------------------

    async def type_uid(self, slug: str) -> str | None:
        found = await rows("MATCH (t:EffectorType {slug_fr: $slug}) RETURN t.uid", slug=slug)
        return found[0][0] if len(found) == 1 else None

    async def commune_uid(self, name: str) -> str | None:
        found = await rows("MATCH (c:Commune {name_fr: $name}) RETURN c.uid", name=name)
        return found[0][0] if len(found) == 1 else None

    async def preflight(self, data: dict, planned: list[PlannedEntry]) -> list[str]:
        problems = []
        self.types = {}
        for slug in {p.type_slug for p in planned} | {ORGANIZATION_TYPE}:
            self.types[slug] = await self.type_uid(slug)
            if self.types[slug] is None:
                problems.append(f"effector type '{slug}' is missing or not unique")
        # The site words each occupation from its labels, singular and plural;
        # a type without them breaks the team and directory pages.
        for slug, uid in self.types.items():
            if uid is None:
                continue
            numbers = {n async for n in Label.objects.filter(uid=uid, language="fr").values_list("grammatical_number", flat=True)}
            if not {"S", "P"} <= numbers:
                problems.append(f"effector type '{slug}' has no French labels (singular and plural)")
        self.communes = {}
        for facility in data["facilities"]:
            for address in facility["contact"]["addresses"][:1]:
                city = address["city"]
                self.communes[city] = await self.commune_uid(city)
                if self.communes[city] is None:
                    problems.append(f"commune '{city}' is missing or not unique")
        old_names = {f["name"] for f in data["facilities"]}
        for p in planned:
            if p.facility not in old_names:
                problems.append(f"{name_of(p.worker)}: unknown facility '{p.facility}'")
        if self.options["main_facility"] not in old_names:
            problems.append(f"unknown main facility '{self.options['main_facility']}'")
        roles = {r async for r in Role.objects.values_list("name", flat=True)}
        if PUBLIC_ROLE not in roles:
            problems.append(f"role '{PUBLIC_ROLE}' is missing")
        self.roles = {r.name: r async for r in Role.objects.all()}
        self.author = None
        if any(
            PUBLIC_ROLE in profile["roles"]
            for w in data["workers"] if w["contact"] for profile in w["contact"]["profiles"]
        ):
            email = self.options["changed_by"]
            self.author = await User.objects.filter(email=email).afirst() if email else None
            if self.author is None:
                problems.append("profiles to import: --changed-by must name an existing user")
        if not await Category.objects.filter(name=data["organization"]["category"]).aexists():
            problems.append(f"category '{data['organization']['category']}' is missing")
        return problems

    # --- bootstrap: Site, Directory, Organization --------------------------

    async def bootstrap(self, data: dict):
        org_data = data["organization"]
        self.site, _ = await Site.objects.aget_or_create(
            domain=self.options["site"], defaults={"name": self.options["site"]}
        )
        name = self.options["directory"]
        node = await AsyncDirectory.nodes.get_or_none(name=name)
        if node is None:
            node = await AsyncDirectory(name=name).save()
        self.directory, _ = await Directory.objects.aget_or_create(
            name=name,
            defaults={
                "uid": uuid.UUID(node.uid),
                "display_name": org_data.get("website_title_fr") or org_data["website_title"],
                "presentation": org_data["website_description"],
                "slug": name,
                "site": self.site,
                "postal_codes": sorted({
                    a["zip"][:2]
                    for f in data["facilities"] for a in f["contact"]["addresses"] if a["zip"]
                }),
                "department_default": True,
                "commune_default": True,
            },
        )
        # The directory's search filters and display, as an MSP's are set.
        await InputField.objects.aget_or_create(
            directory=self.directory,
            defaults={"category": True, "commune": False, "department": False, "facility": True,
                      "geocoder": False, "organization": False, "search": True, "situation": False},
        )
        await Setting.objects.aget_or_create(
            directory=self.directory,
            defaults={"sort_category": "AB", "display_facility_organization": True,
                      "display_association": False, "list_navigation": False,
                      "type_slug": True, "path": "/annuaire"},
        )
        existing = await Organization.objects.filter(site=self.site).afirst()
        if existing and existing.name != self.options["organization"]:
            raise CommandError(f"site {self.site.domain} already belongs to organization '{existing.name}'")
        self.organization = existing or await self.create_organization(org_data)
        legal = org_data.get("legal_entities") or []
        if legal and not await LegalEntity.objects.filter(organization=self.organization).aexists():
            await LegalEntity.objects.acreate(organization=self.organization, **legal[0])

    async def create_organization(self, org_data: dict) -> Organization:
        fields = {f.name for f in Organization._meta.get_fields()}
        values = {
            k: v for k, v in org_data.items()
            if k in fields and k not in ("category", "city") and isinstance(v, str)
        }
        # The untranslated field holds the default language, French here.
        for base in ("formatted_name", "formatted_name_definite_article", "website_title"):
            if org_data.get(f"{base}_fr"):
                values[base] = org_data[f"{base}_fr"]
        # A name, not mid-sentence text: that is the definite article variant.
        values["formatted_name"] = values["formatted_name"][:1].upper() + values["formatted_name"][1:]
        values.setdefault("formatted_name_short", f"MSP {org_data['city']}")
        values["name"] = self.options["organization"]
        organization = Organization(
            **values,
            active=True,
            site=self.site,
            directory=self.directory,
            category=await Category.objects.aget(name=org_data["category"]),
            city=await City.objects.filter(name=org_data["city"]).afirst(),
        )
        await organization.asave()
        return organization

    # --- facilities ---------------------------------------------------------

    async def facility(self, old: dict) -> str:
        address = old["contact"]["addresses"][0]
        slug = slugify(old["contact"]["formatted_name"])
        found = await rows(
            "MATCH (f:Facility {slug: $slug, street: $street, zip: $zip}) RETURN f.uid",
            slug=slug, street=address["street"], zip=address["zip"],
        )
        if found:
            self.report.reused["facility"] += 1
            return found[0][0]
        node = await AsyncFacility(
            name=old["contact"]["formatted_name"],
            label="",
            slug=slug,
            street=address["street"],
            zip=address["zip"],
            zoom=address["zoom"] or 18,
        ).save()
        params = {"uid": node.uid, "commune": self.communes[address["city"]]}
        await rows(
            "MATCH (f:Facility {uid: $uid}), (c:Commune {uid: $commune}) "
            "MERGE (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)",
            **params,
        )
        if address["latitude"] and address["longitude"]:
            await rows(
                "MATCH (f:Facility {uid: $uid}) "
                "SET f.location = point({latitude: $lat, longitude: $lon, crs: 'wgs-84'})",
                uid=node.uid, lat=float(address["latitude"]), lon=float(address["longitude"]),
            )
        self.report.created["facility"] += 1
        return node.uid

    # --- people -------------------------------------------------------------

    async def effector(self, name: str, gender: str | None, rpps: str | None, label: str | None = None) -> str:
        if rpps:
            found = await rows("MATCH (h:HealthWorker {rpps: $rpps}) RETURN h.uid", rpps=int(rpps))
            if found:
                self.report.reused["effector"] += 1
                return found[0][0]
        slug = slugify(name)
        found = await rows(
            "MATCH (x:Effector {creator_directory: $dir, slug_fr: $slug}) RETURN x.uid",
            dir=self.options["directory"], slug=slug,
        )
        if found:
            self.report.reused["effector"] += 1
            return found[0][0]
        node = await AsyncEffector(
            name_fr=name,
            label_fr=label or name,
            slug_fr=slug,
            gender=gender,
            creator_directory=self.options["directory"],
        ).save()
        self.report.created["effector"] += 1
        return node.uid

    async def entry(self, effector_uid: str, type_slug: str, facility_uid: str, props: dict) -> str:
        found = await rows(
            "MATCH (x:Effector {uid: $x})<-[:HAS_EFFECTOR]-(e:Entry)-[:HAS_EFFECTOR_TYPE]->"
            "(:EffectorType {uid: $t}), (e)-[:HAS_FACILITY]->(:Facility {uid: $f}) RETURN e.uid",
            x=effector_uid, t=self.types[type_slug], f=facility_uid,
        )
        if found:
            uid = found[0][0]
            self.report.reused["entry"] += 1
        else:
            node = await AsyncEntry(**props).save()
            uid = node.uid
            await rows(
                "MATCH (e:Entry {uid: $e}), (x:Effector {uid: $x}), (t:EffectorType {uid: $t}), "
                "(f:Facility {uid: $f}) "
                "MERGE (e)-[:HAS_EFFECTOR]->(x) MERGE (e)-[:HAS_EFFECTOR_TYPE]->(t) "
                "MERGE (e)-[:HAS_FACILITY]->(f)",
                e=uid, x=effector_uid, t=self.types[type_slug], f=facility_uid,
            )
            self.report.created["entry"] += 1
        await rows(
            "MATCH (d:Directory {name: $d}), (e:Entry {uid: $e}) MERGE (d)-[:HAS_ENTRY]->(e)",
            d=self.options["directory"], e=uid,
        )
        entry = await AsyncEntry.nodes.get(uid=uid)
        effector_type = await AsyncEffectorType.nodes.get(uid=self.types[type_slug])
        if not entry.slug:
            effector = await AsyncEffector.nodes.get(uid=effector_uid)
            facility = await AsyncFacility.nodes.get(uid=facility_uid)
            slugs = await generate_entry_slugs(effector, facility, effector_type, count=1)
            if not slugs:
                raise CommandError(f"no free slug for entry {uid}")
            entry.slug = slugs[0]
            await entry.save()
        await ensure_health_worker_label(effector_uid, effector_type)
        problems = await entry_shape_problems(uid)
        if problems:
            raise CommandError(f"entry {uid} is malformed: {problems}")
        return uid

    # --- contacts -----------------------------------------------------------

    async def contact(self, neomodel_uid: str, old: dict | None) -> Contact:
        contact, _ = await Contact.objects.aget_or_create(neomodel_uid=uuid.UUID(neomodel_uid))
        if not old:
            return contact
        await self.fill_contact(contact, old)
        return contact

    def role_set(self, names: list[str]) -> list[Role]:
        return [self.roles[n] for n in names if n in self.roles]

    async def add_item(self, model, contact: Contact, lookup: dict, extra: dict, roles: list[str]):
        item, created = await model.objects.aget_or_create(contact=contact, **lookup, defaults=extra)
        if created:
            await item.roles.aset(self.role_set(roles))
            await item.organization.aset([self.organization])

    async def fill_contact(self, contact: Contact, old: dict):
        phone_types = {c for c, _ in PhoneNumber.TelephoneType.choices}
        social_types = {c for c, _ in SocialNetwork.SocialNetworkType.choices}
        who = old["formatted_name"]
        for p in old["phones"]:
            if p["type"] not in phone_types:
                self.report.dropped.append(f"{who}: phone {p['phone']} of type {p['type']}")
                continue
            await self.add_item(
                PhoneNumber, contact, {"phone": p["phone"]},
                {"type": p["type"], "public_visible": p["public_visible"],
                 "contact_visible": p["contact_visible"]}, p["roles"],
            )
        for e in old["emails"]:
            await self.add_item(
                Email, contact, {"email": e["email"]},
                {"public_visible": e["public_visible"], "contact_visible": e["contact_visible"]},
                e["roles"],
            )
        for w in old["websites"]:
            await self.add_item(
                Website, contact, {"url": w["url"]},
                {"public_visible": w["public_visible"], "contact_visible": w["contact_visible"]},
                w["roles"],
            )
        for s in old["socialnetworks"]:
            if s["type"] not in social_types:
                self.report.dropped.append(f"{who}: social network {s['url'] or s['handle']} of type {s['type']}")
                continue
            await self.add_item(
                SocialNetwork, contact, {"type": s["type"], "handle": s["handle"], "url": s["url"]},
                {"public_visible": s["public_visible"], "contact_visible": s["contact_visible"]},
                s["roles"],
            )
        for profile in old["profiles"][:1]:
            # The API serves a profile to anyone, whatever its roles, so one
            # the old site kept from the public stays behind.
            if PUBLIC_ROLE not in profile["roles"]:
                self.report.dropped.append(f"{who}: profile restricted to {', '.join(profile['roles'])}")
                continue
            item, created = await Profile.objects.aget_or_create(
                contact=contact,
                defaults={"text": profile["text"], "organization": self.organization,
                          "changed_by": self.author},
            )
            if created:
                await item.roles.aset(self.role_set(profile["roles"]))
        if old["profile_image"] and not contact.profile_image:
            await sync_to_async(self.copy_avatar)(contact, old["profile_image"], who)

    def copy_avatar(self, contact: Contact, path: str, who: str):
        media_dir = self.options["media_dir"]
        source = os.path.join(media_dir, path) if media_dir else None
        if not source or not os.path.exists(source):
            self.report.dropped.append(f"{who}: avatar {path} not found in --media-dir")
            return
        with open(source, "rb") as f:
            contact.profile_image.save(os.path.basename(path), File(f), save=True)

    async def appointments(self, entry_uid: str, old: dict | None):
        for a in (old or {}).get("appointments", []):
            if a["app"]:
                self.report.dropped.append(f"{old['formatted_name']}: appointment app {a['app']}")
                continue
            value = {"url": a["url"]} if a["url"] else {"phone": a["phone"]}
            key, val = next(iter(value.items()))
            found = await rows(
                f"MATCH (:Entry {{uid: $e}})-[:HAS_APPOINTMENT]->(a:Appointment {{{key}: $v}}) RETURN a.uid",
                e=entry_uid, v=val,
            )
            if found:
                continue
            node = await AsyncAppointment(**value).save()
            await rows(
                "MATCH (e:Entry {uid: $e}), (a:Appointment {uid: $a}) MERGE (e)-[:HAS_APPOINTMENT]->(a)",
                e=entry_uid, a=node.uid,
            )

    async def old_slug(self, slug: str, entry_uid: str):
        existing = await EntrySlug.objects.filter(slug=slug).afirst()
        if existing and existing.entry_uid != entry_uid:
            self.report.dropped.append(f"old slug {slug} already redirects to entry {existing.entry_uid}")
            return
        if not existing:
            await EntrySlug.objects.acreate(slug=slug, entry_uid=entry_uid, replaced_by="import_entries")
        entry = await AsyncEntry.nodes.get(uid=entry_uid)
        self.report.redirects[f"/{slug}"] = f"/e/{entry.slug}"

    # --- run ----------------------------------------------------------------

    def print_plan(self, data: dict, planned: list[PlannedEntry]):
        facilities = {f["name"]: f["contact"]["formatted_name"] for f in data["facilities"]}
        self.say(f"Organization entry: {ORGANIZATION_TYPE} at {facilities[self.options['main_facility']]}")
        self.say(f"{len(data['facilities'])} facilities, {len(data['workers'])} people, {len(planned)} entries:")
        for p in planned:
            flags = "" if p.active else "  [inactive]"
            slug = f"  /{p.old_slug}" if p.old_slug else ""
            self.say(f"  {name_of(p.worker):32} {p.type_slug:28} {facilities[p.facility]}{slug}{flags}")
        for w in data["workers"]:
            if w["adeli"]:
                self.report.dropped.append(f"{name_of(w)}: ADELI {w['adeli']} (no ADELI in the graph)")

    async def run(self, data: dict):
        main = self.options["main_facility"]
        planned, problems = plan_entries(data, main)
        problems += await self.preflight(data, planned)
        if problems:
            for problem in problems:
                self.say(problem, self.style.ERROR)
            raise CommandError(f"{len(problems)} problem(s), nothing written")
        self.print_plan(data, planned)
        if self.options["dry_run"]:
            for line in self.report.dropped:
                self.say(f"  will not import: {line}", self.style.WARNING)
            self.say("--dry-run: nothing written", self.style.WARNING)
            return

        await self.bootstrap(data)
        facility_uids = {f["name"]: await self.facility(f) for f in data["facilities"]}

        org_data = data["organization"]
        org_effector = await self.effector(
            org_data.get("website_title_fr") or org_data["website_title"], "N", None,
            label=f"MSP {org_data['city']}",
        )
        org_entry = await self.entry(
            org_effector, ORGANIZATION_TYPE, facility_uids[main], {"active": True}
        )
        if self.organization.neomodel_uid and self.organization.neomodel_uid.hex != org_entry:
            raise CommandError(
                f"organization already points at entry {self.organization.neomodel_uid.hex}, not {org_entry}"
            )
        org_contact = await self.contact(org_entry, org_data["contact"])
        self.organization.neomodel_uid = uuid.UUID(org_entry)
        self.organization.contact = org_contact
        await self.organization.asave()
        for f in data["facilities"]:
            await rows(
                "MATCH (f:Facility {uid: $f}), (e:Entry {uid: $e}) MERGE (f)-[:PART_OF]->(e)",
                f=facility_uids[f["name"]], e=org_entry,
            )
            await self.contact(facility_uids[f["name"]], f["contact"])

        people = {}
        for p in planned:
            w = p.worker
            healthcare = await rows(
                "MATCH (t:EffectorType {uid: $t}) RETURN 'HCW' IN labels(t)", t=self.types[p.type_slug]
            )
            # One person, one Effector, whichever entry found or made it first.
            effector = people.get(w["user"]["id"]) or await self.effector(
                name_of(w), GENDERS.get(w["user"]["grammatical_gender"]),
                w["rpps"] if healthcare[0][0] else None,
            )
            people[w["user"]["id"]] = effector
            props = {"active": p.active}
            if not p.secondary:
                props |= {
                    "carte_vitale": w["carte_vitale"],
                    "payment": w["payment"] or None,
                    "third_party_payer": w["third_party_payer"] or None,
                    "convention": w["convention"],
                }
            entry = await self.entry(effector, p.type_slug, facility_uids[p.facility], props)
            # Everyone the old site listed belonged to the organization; skcms
            # counts an entry as the MSP's own only through this edge.
            await rows(
                "MATCH (e:Entry {uid: $e}), (o:Entry {uid: $o}) MERGE (e)-[:MEMBER_OF]->(o)",
                e=entry, o=org_entry,
            )
            if healthcare[0][0]:
                await rows(
                    "MATCH (h:HealthWorker {uid: $x}) "
                    "SET h.rpps = coalesce(h.rpps, $rpps), "
                    "h.spoken_languages = coalesce(h.spoken_languages, $langs)",
                    x=effector, rpps=int(w["rpps"]) if w["rpps"] else None,
                    langs=w["spoken_languages"] or None,
                )
            await self.contact(entry, w["contact"])
            if not p.secondary:
                await self.appointments(entry, w["contact"])
            if p.old_slug:
                await self.old_slug(p.old_slug, entry)

        for endpoint in ("v2:entries", "v2:effector-type-labels", "v1:facilities", "v2:public/facilities"):
            await clear_cache(endpoint, site=self.site)
        self.print_report()

    def print_report(self):
        r = self.report
        self.say(f"created {r.created}, reused {r.reused}", self.style.SUCCESS)
        for line in r.dropped:
            self.say(f"  not imported: {line}", self.style.WARNING)
        if self.options["redirects_out"]:
            with open(self.options["redirects_out"], "w") as f:
                json.dump(r.redirects, f, ensure_ascii=False, indent=2, sort_keys=True)
            self.say(f"{len(r.redirects)} redirects written to {self.options['redirects_out']}")
