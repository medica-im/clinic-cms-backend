import logging
from fastapi import APIRouter, HTTPException, Request, status
from neomodel import adb
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.cache import cache
from api.utils import (
    DEFAULT_TTL as _DEFAULT_TTL,
    get_site_from_request,
    resolve_ttl,
    set_timestamp,
)
from api.types.public_facility import Address, PublicFacility
from directory.models.api import TTL, Endpoint
from directory.utils import (
    async_get_directory_for_site,
    async_get_phones_neomodel,
    async_get_emails_neomodel,
    async_get_socialnetworks_neomodel,
    async_get_websites_neomodel,
    async_get_avatar_url,
)

logger = logging.getLogger(__name__)

router = APIRouter()

CACHE_ENDPOINT = "v2:public/facilities"
# The fallback lives in api.utils so all three cached endpoints answer "how
# long, when nobody has said" with the same number. This was 60.
DEFAULT_TTL = _DEFAULT_TTL


async def _get_place_image(uid: str) -> dict | None:
    """
    The facility's wide photograph, or None.

    Separate from async_get_avatar_url: that one reads addressbook.Contact,
    whose renditions are square. A few facilities still have a picture there
    (see the migrate_facility_images command); they keep being served as
    "avatar" until they are moved over.
    """
    from facility.models import PlaceImage as PlaceImageModel

    try:
        place = await PlaceImageModel.objects.aget(neomodel_uid=uid)
    except PlaceImageModel.DoesNotExist:
        return None
    if not place.image:
        return None

    def url(alias):
        try:
            return place.image[alias].url
        except Exception as e:
            logger.error(f"place image {alias} error: {e}")
            return None

    get_urls = sync_to_async(lambda: {
        "sm": url("place_sm"),
        "lg": url("place_lg"),
        "raw": place.image.url,
        "alt": place.alt,
    })
    return await get_urls()


async def _get_ttl(site):
    try:
        endpoint = await Endpoint.objects.aget(name=CACHE_ENDPOINT)
    except Endpoint.DoesNotExist:
        logger.warning(
            "no Endpoint row named %s; falling back to the default TTL",
            CACHE_ENDPOINT,
        )
        return DEFAULT_TTL

    ttl_obj = await TTL.objects.filter(endpoint=endpoint, site=site).afirst()
    if ttl_obj is None:
        logger.warning(
            "no TTL row for endpoint=%s site=%s; falling back to the default",
            CACHE_ENDPOINT, site,
        )
        return DEFAULT_TTL
    # resolve_ttl rather than a truthiness test: a configured 0 means do not
    # cache, and `if ttl_obj:` on the value would have silently become 60.
    return resolve_ttl(ttl_obj.ttl, DEFAULT_TTL)


async def _get_facility_nodes(
    directory_name: str,
    slug: str | None = None,
    uid: str | None = None,
):
    if slug:
        query = """
        MATCH (d:Directory)-[:HAS_ENTRY]->(e:Entry),
              (e)-[:HAS_EFFECTOR]->(:Effector),
              (e)-[:HAS_FACILITY]->(f:Facility)
                -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(commune:Commune)
                -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY*]->(country:Country)
        WHERE f.slug = $slug AND d.name = $directory AND e.active = true
        RETURN f, commune, country
        """
        params = {"slug": slug, "directory": directory_name}
    elif uid:
        query = """
        MATCH (d:Directory)-[:HAS_ENTRY]->(e:Entry),
              (e)-[:HAS_EFFECTOR]->(:Effector),
              (e)-[:HAS_FACILITY]->(f:Facility)
                -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(commune:Commune)
                -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY*]->(country:Country)
        WHERE f.uid = $uid AND d.name = $directory AND e.active = true
        RETURN f, commune, country
        """
        params = {"uid": uid, "directory": directory_name}
    else:
        query = """
        MATCH (d:Directory)-[:HAS_ENTRY]->(e:Entry),
              (e)-[:HAS_EFFECTOR]->(:Effector),
              (e)-[:HAS_FACILITY]->(f:Facility)
                -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(commune:Commune)
                -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY*]->(country:Country)
        WHERE d.name = $directory AND e.active = true
        RETURN DISTINCT f, commune, country
        """
        params = {"directory": directory_name}
    results, _ = await adb.cypher_query(query, params, resolve_objects=True)
    return results


async def _get_facility_orgs_and_entries(facility_uid: str):
    query = """
    MATCH (f:Facility {uid: $uid})
    OPTIONAL MATCH (f)-[:PART_OF]->(org:Organization)
    OPTIONAL MATCH (f)-[:PART_OF]->(org_entry:Entry)
    OPTIONAL MATCH (f)<-[:HAS_FACILITY]-(entry:Entry)
    RETURN collect(DISTINCT org.uid) AS org_uids,
           collect(DISTINCT org_entry.uid) AS org_entry_uids,
           collect(DISTINCT entry.uid) AS entry_uids
    """
    results, _ = await adb.cypher_query(query, {"uid": facility_uid})
    if not results:
        return [], []
    row = results[0]
    organizations = [u for u in row[0] if u] + [u for u in row[1] if u]
    entries = [u for u in row[2] if u]
    return organizations, entries


def _get_address(facility, commune, country) -> Address:
    if facility.location:
        longitude = facility.location.longitude
        latitude = facility.location.latitude
    else:
        longitude = None
        latitude = None
    return Address(
        facility_uid=facility.uid,
        country=country.name,
        city=getattr(commune, 'name_fr', None),
        zip=facility.zip,
        geographical_complement=facility.geographical_complement,
        street=facility.street,
        building=facility.building,
        longitude=longitude,
        latitude=latitude,
        zoom=facility.zoom,
        tooltip_direction=getattr(facility, 'tooltip_direction', None),
        tooltip_permanent=getattr(facility, 'tooltip_permanent', None),
    )


async def _serialize_facility(facility, commune, country) -> PublicFacility:
    name = facility.name
    if not name:
        try:
            orgs_query = """
            MATCH (f:Facility {uid: $uid})-[:PART_OF]->(org:Organization)
            RETURN org
            """
            results, _ = await adb.cypher_query(
                orgs_query, {"uid": facility.uid}, resolve_objects=True
            )
            if results:
                org = results[0][0]
                name = getattr(
                    org,
                    f'name_{settings.LANGUAGE_CODE}',
                    getattr(org, 'label_en', None)
                )
        except Exception:
            name = None

    organizations, entries = await _get_facility_orgs_and_entries(facility.uid)
    address = _get_address(facility, commune, country)
    phones = await async_get_phones_neomodel(facility=facility)
    emails = await async_get_emails_neomodel(f=facility)
    websites = await async_get_websites_neomodel(f=facility)
    socialnetworks = await async_get_socialnetworks_neomodel(facility=facility)
    avatar = await async_get_avatar_url(f=facility)
    image = await _get_place_image(facility.uid)

    return PublicFacility.model_validate({
        "uid": facility.uid,
        "name": name,
        "label": getattr(facility, 'label', name),
        "slug": facility.slug,
        "commune": getattr(commune, 'uid', None),
        "address": address,
        "organizations": organizations,
        "phones": phones,
        "emails": emails,
        "websites": websites,
        "socialnetworks": socialnetworks,
        "avatar": avatar,
        "image": image,
        "entries": entries,
        "ban_id": getattr(facility, 'ban_id', None),
        "ban_banId": getattr(facility, 'ban_banId', None),
    })


@router.get("/public/facilities")
async def public_facilities(request: Request) -> list[PublicFacility]:
    site = await get_site_from_request(request)
    cache_key = f"{CACHE_ENDPOINT}:{site.domain}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    directory = await async_get_directory_for_site(site)
    rows = await _get_facility_nodes(directory.name)
    results = []
    for row in rows:
        facility, commune, country = row
        results.append(await _serialize_facility(facility, commune, country))
    ttl = await _get_ttl(site)
    cache.set(cache_key, results, timeout=ttl)
    await set_timestamp(CACHE_ENDPOINT, site)
    return results


@router.get("/public/facilities/{slug}")
async def public_facility(slug: str, request: Request) -> PublicFacility:
    site = await get_site_from_request(request)
    directory = await async_get_directory_for_site(site)
    rows = await _get_facility_nodes(directory.name, slug=slug)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Facility {slug} not found",
        )
    facility, commune, country = rows[0]
    return await _serialize_facility(facility, commune, country)


@router.get("/public/facilitiesuid/{uid}")
async def public_facility_by_uid(uid: str, request: Request) -> PublicFacility:
    site = await get_site_from_request(request)
    directory = await async_get_directory_for_site(site)
    rows = await _get_facility_nodes(directory.name, uid=uid)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Facility {uid} not found",
        )
    facility, commune, country = rows[0]
    return await _serialize_facility(facility, commune, country)
