"""Every route's answer, recorded so that an upgrade can be compared to it.

Not a test: it calls each of the app's routes in-process against the dev
stack's own graph and database, which hold the data the frontends see, and
writes what came back to a JSON file. Run it before an upgrade (twice), then
after, and compare:

    docker exec -w /app backend-dev-fastapi-1 python -m tests.route_snapshot record /tmp/before-1.json
    docker exec -w /app backend-dev-fastapi-1 python -m tests.route_snapshot record /tmp/before-2.json
    ... upgrade, rebuild ...
    docker exec -w /app backend-dev-fastapi-1 python -m tests.route_snapshot record /tmp/after.json
    docker exec -w /app backend-dev-fastapi-1 python -m tests.route_snapshot compare /tmp/before-1.json /tmp/before-2.json /tmp/after.json

A route whose answer differs between the two "before" runs is volatile (a
timestamp, an external lookup) and is reported apart from the regressions.

Routes come from the OpenAPI schema rather than app.routes, which FastAPI
0.137 turned from a list into a tree. Each is called as anonymous, staff,
administrator and superuser of SITE, whose accounts are the real ones in the
dev graph. GET routes are given real path parameters. Writes are given a
parameter that matches nothing and no body: they record the refusal or the
validation error, and change no data. The few writes that would act even then
are in SKIPPED.
"""
import asyncio
import json
import os
import re
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

import django  # noqa: E402

django.setup()

from asgiref.sync import sync_to_async  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from neomodel import adb  # noqa: E402

SITE = "dev.santelyon3.fr"
ROLES = ("anonymous", "staff", "administrator", "superuser")
MISSING = "snapshot-missing"
TIMEOUT = 30  # seconds; a call that takes longer is recorded as a TimeoutError

# Writes that act without a body or a path parameter.
SKIPPED = {
    ("DELETE", "/invitees"),  # without ids, deletes every invitee of the site
    ("DELETE", "/clone/export-token"),  # burns the export token
}


async def one(query, **params):
    rows, _ = await adb.cypher_query(query, params)
    return rows[0][0] if rows else MISSING


async def first_id(model):
    obj = await model.objects.order_by("id").afirst()
    return str(obj.id) if obj else MISSING


async def path_values() -> dict[str, dict[str, str]]:
    """Real values for each GET route's path parameters, the same on every run."""
    from access.models import BatchInviteeJob
    from addressbook.models import Email, PhoneNumber, SocialNetwork, Website
    from directory.models import EntrySlug
    from facility.models import Organization
    from django.contrib.sites.models import Site

    organization = await Organization.objects.aget(site=await Site.objects.aget(domain=SITE))
    org_uid = organization.neomodel_uid.hex

    entry = await adb.cypher_query(
        """MATCH (e:Entry {active: true})-[:HAS_FACILITY]->(f:Facility)
                 -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune),
                 (e)-[:HAS_EFFECTOR]->(ef:Effector), (e)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType)
           WHERE e.slug IS NOT NULL AND f.slug IS NOT NULL
           RETURN e.uid, e.slug, f.uid, f.slug, c.slug_fr, ef.uid, ef.slug_fr, et.uid, et.slug_fr
           ORDER BY e.uid LIMIT 1"""
    )
    e_uid, e_slug, f_uid, f_slug, c_slug, ef_uid, ef_slug, et_uid, et_slug = (
        entry[0][0] if entry[0] else [MISSING] * 9
    )
    former = await EntrySlug.objects.order_by("id").afirst()
    job = await BatchInviteeJob.objects.filter(organization_neomodel_uid=org_uid).order_by("id").afirst()
    user_uid = await one(
        """MATCH (u:User)-[:HAS_ACCESS]->(:Access {active: true})-[:ACCESS_TO]->(:Entry {uid: $org})
           RETURN u.uid ORDER BY u.uid LIMIT 1""",
        org=org_uid,
    )

    return {
        "/carehomes/{uid}": {"uid": await one("MATCH (n:CareHome) RETURN n.uid ORDER BY n.uid LIMIT 1")},
        "/communes/{uid}": {"uid": await one("MATCH (n:Commune) RETURN n.uid ORDER BY n.uid LIMIT 1")},
        "/departments/{uid}": {"uid": await one("MATCH (n:DepartmentOfFrance) RETURN n.uid ORDER BY n.uid LIMIT 1")},
        "/effector-types/{uid}": {"uid": et_uid},
        "/effector-types/{uid}/labels": {"uid": et_uid},
        "/effectors/{uid}": {"uid": ef_uid},
        "/entries/{uid}/effector-type/permission": {"uid": e_uid},
        "/entries/{uid}/effector-type/preview": {"uid": e_uid},
        "/entry-slugs/{slug}": {"slug": former.slug if former else MISSING},
        "/facilities/{uid}": {"uid": f_uid},
        "/facilities/{uid}/can-edit": {"uid": f_uid},
        "/facilities-slug/{slug}": {"slug": f_slug},
        "/public/facilities/{slug}": {"slug": f_slug},
        "/public/facilitiesuid/{uid}": {"uid": f_uid},
        "/fullentries/{uid}": {"uid": e_uid},
        "/fullentries/slug/{slug}": {"slug": e_slug},
        "/slugfullentries/{type}/{commune}/{effector}": {"type": et_slug, "commune": c_slug, "effector": ef_slug},
        "/ftefullentries/{facility}/{type}/{effector}": {"facility": f_slug, "type": et_slug, "effector": ef_slug},
        "/invitees/{invitee_uid}": {"invitee_uid": await one(
            "MATCH (:Entry {uid: $org})<-[:INVITED_TO]-(i:Invitee) RETURN i.uid ORDER BY i.uid LIMIT 1", org=org_uid)},
        "/organization-types/{uid}": {"uid": await one("MATCH (n:OrganizationType) RETURN n.uid ORDER BY n.uid LIMIT 1")},
        "/tag_categories/{uid}": {"uid": await one("MATCH (n:TagCategory) RETURN n.uid ORDER BY n.uid LIMIT 1")},
        "/users/{user_uid}": {"user_uid": user_uid},
        "/users/{user_uid}/access-history": {"user_uid": user_uid},
        "/emails/{item_id}": {"item_id": await first_id(Email)},
        "/phones/{item_id}": {"item_id": await first_id(PhoneNumber)},
        "/websites/{item_id}": {"item_id": await first_id(Website)},
        "/socialmedia/{item_id}": {"item_id": await first_id(SocialNetwork)},
        "/email-templates/{kind}": {"kind": "invitation"},
        "/batch-invitees/{job_uid}": {"job_uid": str(job.uid) if job else MISSING},
        "/batch-invitees/{job_uid}/progress": {"job_uid": str(job.uid) if job else MISSING},
    }


async def identities() -> dict[str, dict | None]:
    """The JWT each role is called with: a real account of SITE holding it."""
    from facility.models import Organization
    from django.contrib.sites.models import Site

    organization = await Organization.objects.aget(site=await Site.objects.aget(domain=SITE))
    rows, _ = await adb.cypher_query(
        """MATCH (a:Account)<-[:HAS_ACCOUNT]-(u:User)-[:HAS_ACCESS]->(ac:Access {active: true})
                 -[:ACCESS_TO]->(:Entry {uid: $org})
           WITH ac.role AS role, a, u ORDER BY a.sub
           RETURN role, collect(a.sub)[0], collect(u.email)[0]""",
        {"org": organization.neomodel_uid.hex},
    )
    found = {role: (sub, email) for role, sub, email in rows}
    jwts: dict[str, dict | None] = {"anonymous": None}
    for role in ROLES[1:]:
        if role not in found:
            sys.exit(f"{SITE} has no active {role} account in the dev graph")
        sub, email = found[role]
        jwts[role] = {"providerAccountId": sub, "sub": sub, "email": email or "", "name": role}
    return jwts


def fill(path: str, values: dict[str, str] | None) -> str:
    return re.sub(r"\{([^}]+)\}", lambda m: (values or {}).get(m.group(1), MISSING), path)


async def record(out: str) -> None:
    from api.auth import JWT, check_cookie_jwt
    from main import app

    spec = app.openapi()["paths"]
    values = await path_values()
    jwts = await identities()
    result: dict[str, dict] = {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url=f"http://{SITE}") as client:
        for path in sorted(spec):
            for method in sorted(spec[path]):
                method = method.upper()
                key = f"{method} {path}"
                if (method, path) in SKIPPED:
                    result[key] = {"skipped": True}
                    continue
                url = fill(path, values.get(path) if method == "GET" else None)
                result[key] = {}
                for role in ROLES:
                    if jwts[role] is None:
                        app.dependency_overrides.pop(JWT, None)
                        app.dependency_overrides.pop(check_cookie_jwt, None)
                    else:
                        app.dependency_overrides[JWT] = lambda j=jwts[role]: j
                        app.dependency_overrides[check_cookie_jwt] = lambda j=jwts[role]: j
                    print(f"{key} as {role}", file=sys.stderr, flush=True)
                    try:
                        response = await asyncio.wait_for(
                            client.request(method, url, follow_redirects=False), TIMEOUT
                        )
                        try:
                            body = response.json()
                        except ValueError:
                            body = response.text
                        result[key][role] = {"status": response.status_code, "body": body}
                    except Exception as e:  # noqa: BLE001 - a crash is an answer too
                        result[key][role] = {"exception": f"{type(e).__name__}: {e}"}
    app.dependency_overrides.clear()
    with open(out, "w") as f:
        json.dump({"site": SITE, "values": values, "routes": result}, f, indent=1, sort_keys=True, default=str)
    calls = sum(len(v) for v in result.values() if "skipped" not in v)
    print(f"{len(result)} operations, {calls} calls -> {out}")


def compare(before_1: str, before_2: str, after: str) -> int:
    b1, b2, a = (json.load(open(p))["routes"] for p in (before_1, before_2, after))
    volatile, changed = [], []
    for key in sorted(set(b1) | set(a)):
        if key not in a:
            changed.append(f"{key}: gone")
            continue
        if key not in b1:
            changed.append(f"{key}: new")
            continue
        for role in sorted(set(b1[key]) | set(a[key])):
            x, y = b1[key].get(role), a[key].get(role)
            if x == y:
                continue
            target = volatile if b1[key].get(role) != b2.get(key, {}).get(role) else changed
            target.append(f"{key} as {role}: {summary(x)} -> {summary(y)}")
    print(f"{len(changed)} change(s), {len(volatile)} on volatile routes")
    for line in changed:
        print("  " + line)
    if volatile:
        print("volatile (differ between the two 'before' runs too):")
        for line in volatile:
            print("  " + line)
    return 1 if changed else 0


def summary(answer) -> str:
    if not isinstance(answer, dict):
        return repr(answer)
    if "exception" in answer:
        return answer["exception"][:200]
    if "skipped" in answer:
        return "skipped"
    body = json.dumps(answer.get("body"), sort_keys=True, default=str)
    return f"{answer.get('status')} {body[:300]}"


if __name__ == "__main__":
    match sys.argv[1:]:
        case ["record", out]:
            asyncio.run(record(out))
        case ["compare", before_1, before_2, after]:
            sys.exit(compare(before_1, before_2, after))
        case _:
            sys.exit(__doc__)
