import logging
import time
from asgiref.sync import sync_to_async
from django.contrib.sites.shortcuts import get_current_site
from directory.models import (
    Directory,
    Effector,
    CareHome,
    EffectorType,
    Facility,
    EffectorFacility,
    Commune,
    Country,
    ThirdPartyPayer,
    PaymentMethod,
    HealthWorker,
    Entry,
    TTL,
    Timestamp,
    Endpoint,
    Label,
)
from django.contrib.sites.models import Site
from directory.models.graph import Appointment, Office, HouseCall, Convention, Tag, Directory as GraphDirectory
from addressbook.models import Contact
from neomodel import db, adb
from addressbook.api.serializers import (
    PhoneNumberSerializer,
    AsyncPhoneNumberModelSerializer,
    AsyncEmailSerializer,
    EmailSerializer,
    WebsiteSerializer,
    AsyncWebsiteSerializer,
    SocialNetworkSerializer,
    AddressSerializer,
    ProfileSerializer,
    AsyncProfileSerializer,
)
from api.serializers.appointment import AppointmentSerializer
from rest_framework.serializers import ModelSerializer
from django.conf import settings
from django.core.cache import cache
from facility.models import Organization

logger = logging.getLogger(__name__)

def flex_effector_type_label(
        effector,
        effector_type,
    ):
    try:
        effector_type_label=Label.get_label(
            effector_type.uid,
            effector.gender,
            "S",
            settings.LANGUAGE_CODE
        )
    except Label.DoesNotExist as e:
        logger.error(e)
        effector_type_label=None
    return effector_type_label

async def async_flex_effector_type_label(
        effector,
        effector_type,
    ):
    try:
        effector_type_label= await Label.async_get_label(
            effector_type.uid,
            effector.gender,
            "S",
            settings.LANGUAGE_CODE
        )
    except Label.DoesNotExist as e:
        logger.error(e)
        effector_type_label=None
    return effector_type_label

def generate_cache_key(api_name, resource_name, request):
        site=get_current_site(request)
        domain=site.domain
        cache_key = "%s:%s:%s" % (api_name, resource_name, domain)
        return cache_key

def get_ttl(endpoint: str, request):
    site = get_current_site(request)
    try:
        ttl_obj = TTL.objects.filter(endpoint__name=endpoint,site=site).first()
    except TTL.DoesNotExist:
        return
    if ttl_obj:
        return ttl_obj.ttl

def get_directory(request):
    site = get_current_site(request)
    try:
        return Directory.objects.get(site=site)
    except Directory.DoesNotExist:
        raise Directory.DoesNotExist

async def async_get_directory(request):
    site = get_current_site(request)
    try:
        return await Directory.objects.aget(site=site)
    except Directory.DoesNotExist:
        raise Directory.DoesNotExist

def get_contact_related_elements(
        neo_entity,
        attribute,
        many: bool
    ):
    try:
        contact = Contact.objects.get(neomodel_uid=neo_entity.uid)
    except (Contact.DoesNotExist, AttributeError):
        return None
    try:
        related = getattr(contact, attribute)
        if many:
            return list(related.all()) or None
        else:
            return related
    except AttributeError:
        return None

async def async_get_contact_related_elements(
        neo_entity,
        attribute,
        many: bool
    ):
    try:
        contact = await Contact.objects.prefetch_related('phonenumbers', 'phonenumbers__roles', 'emails', 'emails__roles', 'websites', 'websites__roles', 'socialnetworks', 'socialnetworks__roles', 'appointments', 'appointments__roles', 'profile', 'profile__roles').aget(neomodel_uid=neo_entity.uid)
    except (Contact.DoesNotExist, AttributeError):
        return None
    try:
        related = getattr(contact, attribute)
        if many:
            elements=[]
            async for element in related.all():
                elements.append(element)
            return elements or None
        else:
            return related
    except AttributeError:
        return None

def get_contact_related_neomodel(
        entry: Entry|None = None,
        e: Effector|None = None,
        ef: EffectorFacility|None = None,
        f: Facility|None = None,
        attribute: str = "",
        Serializer:  ModelSerializer|None = None,
        many: bool = True,
        first_hit = False,
    ):
    elements = set()
    for neo_entity in [entry, e, ef, f]:
        new_elements = get_contact_related_elements(
            neo_entity=neo_entity,
            attribute=attribute,
            many=many
        )
        if new_elements:
            try:
                elements.add(new_elements)
            except TypeError:
                elements.update(new_elements)
        if len(elements) and first_hit:
            break
    try:
        elements.remove(None)
    except KeyError:
        pass
    if elements:
        try:
            serializer = Serializer(
                elements,
                many=many
            )
        except AttributeError:
            return
        return serializer.data

async def async_get_contact_related_neomodel(
        entry: Entry|None = None,
        e: Effector|None = None,
        ef: EffectorFacility|None = None,
        f: Facility|None = None,
        attribute: str = "",
        Serializer:  ModelSerializer|None = None,
        many: bool = True,
        first_hit = False,
    ):
    elements = set()
    for neo_entity in [entry, e, ef, f]:
        new_elements = await async_get_contact_related_elements(
            neo_entity=neo_entity,
            attribute=attribute,
            many=many
        )
        if new_elements:
            try:
                elements.add(new_elements)
            except TypeError:
                elements.update(new_elements)
        if len(elements) and first_hit:
            break
    try:
        elements.remove(None)
    except KeyError:
        pass
    if elements:
        try:
            serializer = Serializer(
                elements,
                many=many
            )
        except AttributeError:
            return
        return serializer.data

def get_profile_neomodel(entry: Entry, e: Effector, ef: EffectorFacility, f: Facility):
    return get_contact_related_neomodel(
        entry=entry,
        e=e,
        ef=ef,
        f=f,
        attribute="profile",
        Serializer=ProfileSerializer,
        many=False
    )

async def async_get_profile_neomodel(entry: Entry, e: Effector, ef: EffectorFacility, f: Facility):
    return await async_get_contact_related_neomodel(
        entry=entry,
        e=e,
        ef=ef,
        f=f,
        attribute="profile",
        Serializer=AsyncProfileSerializer,
        many=False
    )

def appointments_from_neomodel(entry: str, nodes: list[Appointment]|Appointment):
    def get_location(node: Appointment):
        labels = node.labels()
        if 'HouseCall' in labels:
            return 'house_call'
        elif 'Office' in labels:
            return 'office'
        else:
            return None
    if not nodes or nodes==[[]]:
        return None
    if type(nodes) in [Appointment, Office, HouseCall]:
        nodes = [nodes]
    data = [
        {
            'uid': node.uid,
            'entry': entry,
            'phone': node.phone,
            'url': node.url,
            'location': get_location(node)
        } for node in nodes
    ]
    serializer = AppointmentSerializer(data=data, many=True)
    if serializer.is_valid():
        return serializer.validated_data
    else:
        logger.error(serializer.errors)

def get_websites_neomodel(
        entry: Entry|None=None,
        e: Effector | None = None,
        ef: EffectorFacility | None = None,
        f: Facility | None = None
    ):
    return get_contact_related_neomodel(
        entry=entry,
        e=e,
        ef=ef,
        f=f,
        attribute="websites",
        Serializer=WebsiteSerializer
    )

async def async_get_websites_neomodel(
    entry: Entry|None=None,
    e: Effector | None = None,
    ef: EffectorFacility | None = None,
    f: Facility | None = None
    ):
    return await async_get_contact_related_neomodel(
        entry=entry,
        e=e,
        ef=ef,
        f=f,
        attribute="websites",
        Serializer=AsyncWebsiteSerializer,
        first_hit=False,
        many=True,
    )

def get_socialnetworks_neomodel(
        entry: Entry|None=None,
        e: Effector | None = None,
        ef: EffectorFacility | None = None,
        f: Facility | None = None,
    ):
    return get_contact_related_neomodel(
        entry=entry,
        e=e,
        ef=ef,
        f=f,
        attribute="socialnetworks",
        Serializer=SocialNetworkSerializer
    )

async def async_get_socialnetworks_neomodel(
        entry: Entry|None=None,
        facility: Facility | None = None,
    ):
    return await async_get_contact_related_neomodel(
        entry=entry,
        f=facility,
        attribute="socialnetworks",
        Serializer=SocialNetworkSerializer
    )

def get_phones_neomodel(
        entry: Entry|None = None,
        facility: Facility|None = None,
    ):
    return get_contact_related_neomodel(
        entry=entry,
        f=facility,
        attribute="phonenumbers",
        Serializer=PhoneNumberSerializer,
        first_hit=True,
        many=True,
    )

async def async_get_phones_neomodel(
        entry: Entry|None=None,
        facility: Facility|None=None,
    ):
    return await async_get_contact_related_neomodel(
        entry=entry,
        f=facility,
        attribute="phonenumbers",
        Serializer=AsyncPhoneNumberModelSerializer,
        first_hit=False,
        many=True,
    )

def get_emails_neomodel(
        entry: Entry|None=None,
        e: Effector | None = None,
        ef: EffectorFacility | None = None,
        f: Facility | None = None
    ):
    return get_contact_related_neomodel(
        entry=entry,
        e=e,
        ef=ef,
        f=f,
        attribute="emails",
        Serializer=EmailSerializer,
        first_hit=False,
        many=True,
    )

async def async_get_emails_neomodel(
        entry: Entry|None=None,
        e: Effector | None = None,
        ef: EffectorFacility | None = None,
        f: Facility | None = None
    ):
    return await async_get_contact_related_neomodel(
        entry=entry,
        e=e,
        ef=ef,
        f=f,
        attribute="emails",
        Serializer=AsyncEmailSerializer,
        first_hit=False,
        many=True,
    )

def get_avatar_url(
        entry: Entry|None=None,
        e: Effector | None = None,
        ef: EffectorFacility | None = None,
        f: Facility | None = None
    ):
    def get_avatar_dict(profile_image):
        if not profile_image:
            return
        try:
            fb = profile_image["avatar_facebook"].url
        except:
            fb = None
        try:
            lt = profile_image["avatar_linkedin_twitter"].url
        except:
            lt = None
        try:
            raw = profile_image.url
        except:
            raw = None
        return {
            "fb": fb,
            "lt": lt,
            "raw": raw
        }
    try:
        entry_avatar = Contact.objects.get(neomodel_uid=entry.uid).profile_image
    except (Contact.DoesNotExist, AttributeError):
        entry_avatar = None
    try:
        effector_avatar = Contact.objects.get(neomodel_uid=e.uid).profile_image
    except (Contact.DoesNotExist, AttributeError):
        effector_avatar = None
    try:
        ef_avatar = Contact.objects.get(neomodel_uid=ef.uid).profile_image
    except (Contact.DoesNotExist, AttributeError):
        ef_avatar = None
    try:
        f_avatar = Contact.objects.get(neomodel_uid=f.uid).profile_image
    except (Contact.DoesNotExist, AttributeError):
        f_avatar = None
    if (entry_avatar):
        return get_avatar_dict(entry_avatar)
    if (ef_avatar):
        return get_avatar_dict(ef_avatar)
    if (effector_avatar):
        return get_avatar_dict(effector_avatar)
    if (f_avatar):
        return get_avatar_dict(f_avatar)

async def async_get_avatar_url(
        entry: Entry|None=None,
        e: Effector | None = None,
        ef: EffectorFacility | None = None,
        f: Facility | None = None
    ):
    def get_avatar_dict(profile_image):
        if not profile_image:
            return
        try:
            fb = profile_image["avatar_facebook"].url
        except:
            fb = None
        try:
            lt = profile_image["avatar_linkedin_twitter"].url
        except:
            lt = None
        try:
            raw = profile_image.url
        except:
            raw = None
        return {
            "fb": fb,
            "lt": lt,
            "raw": raw
        }
    try:
        contact = await Contact.objects.aget(neomodel_uid=entry.uid)
        entry_avatar = contact.profile_image
    except (Contact.DoesNotExist, AttributeError):
        entry_avatar = None
    try:
        contact = await Contact.objects.aget(neomodel_uid=e.uid)
        effector_avatar = contact.profile_image
    except (Contact.DoesNotExist, AttributeError):
        effector_avatar = None
    try:
        contact = await Contact.objects.aget(neomodel_uid=ef.uid)
        ef_avatar = contact.profile_image
    except (Contact.DoesNotExist, AttributeError):
        ef_avatar = None
    try:
        contact = await Contact.objects.aget(neomodel_uid=f.uid)
        f_avatar = contact.profile_image
    except (Contact.DoesNotExist, AttributeError):
        f_avatar = None
    if (entry_avatar):
        return get_avatar_dict(entry_avatar)
    if (ef_avatar):
        return get_avatar_dict(ef_avatar)
    if (effector_avatar):
        return get_avatar_dict(effector_avatar)
    if (f_avatar):
        return get_avatar_dict(f_avatar)

def get_address(facility: Facility, commune: Commune, country: Country):
    if facility.location:
        longitude=facility.location.longitude
        latitude=facility.location.latitude
    else:
        longitude=None
        latitude=None
    _dct = {
       "facility_uid": facility.uid,
       "country": country.name,
       "city": commune.name_fr,
       "zip": facility.zip,
       "geographical_complement": facility.geographical_complement,
       "street": facility.street,
       "building": facility.building,
       "longitude": longitude,
       "latitude": latitude,
       "zoom": facility.zoom,
       "tooltip_direction": facility.tooltip_direction,
       "tooltip_permanent": facility.tooltip_permanent,
       "tooltip_direction": facility.tooltip_direction, 
    }
    return _dct

def node_uids(entries):
    if entries and not isinstance(entries, list):
        entries=[entries]
    try:
        return [entry.uid for entry in entries]
    except Exception as e:
        return []

def get_effector_nodes(
        directory: Directory,
        label: str,
        active: bool = True
    ):
    results, cols = db.cypher_query(
        f"""MATCH (e:{label})-[rel:LOCATION]-(f:Facility)
        WHERE rel.directories=["{directory.name}"] AND rel.active={str(active)}
        RETURN e;"""
    )
    effectors = {
        "CareHome": CareHome
    }
    if results:
        nodes=[]
        for row in results:
            node=effectors.get(label).inflate(row[cols.index('e')])
            nodes.append(node)
        return nodes

def get_facilities(
        directory: Directory|None = None,
        uid: str|None = None,
        slug: str|None = None,
        active: bool = True,
    ):
    if uid:
        query=f"""MATCH (f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(commune:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY*]->(country:Country) WHERE f.uid="{uid}" RETURN f,commune,country;"""
    elif slug:
        query=f"""MATCH (d:Directory)-[:HAS_ENTRY]->(e:Entry),(e)-[:HAS_EFFECTOR]->(:Effector),(e)-[:HAS_FACILITY]->(f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(commune:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY*]->(country:Country) WHERE f.slug="{slug}" AND d.name="{directory.name}" AND e.active={str(active).lower()} RETURN f,commune,country;"""
    else:
        query=f"""MATCH (d:Directory)-[:HAS_ENTRY]->(e:Entry),
        (e)-[:HAS_EFFECTOR]->(:Effector),
        (e)-[:HAS_FACILITY]->(f:Facility)-[]->(commune:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY*]->(country:Country)
        WHERE d.name="{directory.name}"
        AND e.active={str(active).lower()}
        RETURN DISTINCT f,commune,country;"""
    results, cols = db.cypher_query(query, resolve_objects = True)
    _facilities=[]
    try:
        for row in results:
            _facilities.append(
                {
                    "facility": row[0],
                    "commune": row[1],
                    "country": row[2]
                }
            )
    except:
        pass
    return _facilities

def directory_contacts(
        directory: Directory,
        uid = None,
        label: str = "Effector",
        active: bool = True,
    ):
    if uid:
        query=f"""
        MATCH (entry:Entry) WHERE entry.uid="{uid}"
        WITH entry
        MATCH (entry)-[:HAS_EFFECTOR]->(e:Effector)
        MATCH (entry)-[:HAS_FACILITY]->(f:Facility)
        RETURN entry,e,f;
        """
    else:
        query=f"""
        MATCH (d:Directory) WHERE d.name="{directory.name}"
        WITH d
        MATCH (d)-[:HAS_ENTRY]->(entry:Entry) WHERE entry.active={str(active)}
        WITH entry
        MATCH (entry)-[:HAS_EFFECTOR]->(e:Effector)
        MATCH (entry)-[:HAS_FACILITY]->(f:Facility)
        RETURN entry,e,f;
        """ 
    results, cols = db.cypher_query(query)
    contacts=[]
    if results:
        for row in results:
            effector=row[cols.index('e')]
            entry=row[cols.index('entry')]
            facility=row[cols.index('f')]
            try:
                timestamp = max(
                    [
                        effector["updatedAt"],
                        entry["contactUpdatedAt"],
                        facility["contactUpdatedAt"]
                    ]
                )
            except Exception as e:
                logger.warn(f'{effector.name_fr}\n{e}')
            contacts.append(
                {
                    "uid": entry["uid"],
                    "timestamp": timestamp
                }
            )
    return contacts

def contact_uids(directory: Directory=None, active=True, search=""):
    if directory:
        directory_query = f'WHERE d.name="{directory.name}"'
    else:
        directory_query = ""
    if search:
        search_query = f'WHERE e.name_fr =~ "(?i).*{search}.*"'
    else:
        search_query = ""
    query=(
        f"""
        MATCH (d:Directory)
        {directory_query}
        WITH d
        MATCH (d)-[:HAS_ENTRY]->(entry:Entry)
        WITH entry
        MATCH (entry)-[:HAS_FACILITY]->(f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune),
        (entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType),
        (entry)-[:HAS_EFFECTOR]->(e:Effector)
        {search_query}
        WITH *
        MATCH (e:Effector)-[rel:LOCATION]->(f:Facility)
        RETURN et,e,rel,f,c;
        """
    )
    results, cols = db.cypher_query(query)
    if results:
        contacts=[]
        for row in results:
            effector=Effector.inflate(row[cols.index('e')])
            location=EffectorFacility.inflate(row[cols.index('rel')])
            facility=Facility.inflate(row[cols.index('f')])
            contacts.append(effector.uid)
            contacts.append(location.uid)
            contacts.append(facility.uid)
        return contacts

def directory_effectors(
        directory: Directory,
        uid = None,
        label: str = "Effector",
        active: bool = True,
    ):
    if uid:
        query=f"""MATCH (et:EffectorType)<-[:IS_A]-(e:{label})-[rel:LOCATION]-(f:Facility)-[]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY*]->(country:Country)
        WHERE rel.directories=["{directory.name}"] AND (rel.uid="{uid}")
        RETURN e,et,rel,f,c,country;"""
    else:
        query=f"""MATCH (et:EffectorType)<-[:IS_A]-(e:{label})-[rel:LOCATION]-(f:Facility)-[]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY*]->(country:Country)
        WHERE rel.directories=["{directory.name}"] AND rel.active={str(active)}
        RETURN e,et,rel,f,c,country;"""
    results, cols = db.cypher_query(query)
    if results:
        effectors=[]
        for row in results:
            effector=Effector.inflate(row[cols.index('e')])
            location=EffectorFacility.inflate(row[cols.index('rel')])
            facility=Facility.inflate(row[cols.index('f')])
            commune=Commune.inflate(row[cols.index('c')])
            country=Country.inflate(row[cols.index('country')])
            types=EffectorType.inflate(row[cols.index('et')])
            types = types if isinstance(types, list) else [types]
            address = get_address(facility,commune,country)
            avatar=get_avatar_url(effector, location, facility)
            effectors.append(
                {
                    "effector": effector,
                    "location": location,
                    "address": address,
                    "commune": commune,
                    "types": types,
                    "facility": facility,
                    "avatar": avatar,
                }
            )
        return effectors

def display(_list):
    for idx,e in enumerate(_list):
        logger.debug(f'{idx}: {e}\n')

def get_entries_query(
    directory: Directory,
    uid = None,
    active: bool = True,
)->str:
    if uid:
        query=f"""MATCH (entry:Entry) WHERE entry.uid="{uid}" WITH entry MATCH (entry)-[:HAS_FACILITY]->(f:Facility)-[]->(commune:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt:DepartmentOfFrance)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY*]->(country:Country) MATCH (entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType) MATCH (entry)-[:HAS_EFFECTOR]->(e:Effector) WITH * OPTIONAL MATCH (e:Effector)-[rel:LOCATION]-(f:Facility)
        OPTIONAL MATCH (entry:Entry)-[:MEMBER_OF]->(o:Organization)
        OPTIONAL MATCH (entry:Entry)-[:MEMBER_OF]->(memberships:Entry)
        OPTIONAL MATCH (entry:Entry)-[:EMPLOYER]->(employer:Organization)
        OPTIONAL MATCH (entry:Entry)-[:EMPLOYER]->(employer_entry:Entry)
        RETURN entry,e,et,f,rel,o,COLLECT(DISTINCT memberships) as memberships,employer,employer_entry,commune,dpt,country;"""
    else:
        query=f"""MATCH (d:Directory) WHERE d.name="{directory.name}"
        WITH d
        MATCH (d)-[:HAS_ENTRY]->(entry:Entry) WHERE entry.active={str(active)}
        WITH entry
        MATCH (entry)<-[:HAS_ENTRY]-(directory:Directory)
        WITH entry, COLLECT(DISTINCT directory) as directories
        MATCH (e:Effector)<-[:HAS_EFFECTOR]-(entry)-[:HAS_FACILITY]->(f:Facility)-[]->(commune:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt:DepartmentOfFrance)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY*]->(country:Country), (entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType)
        WITH DISTINCT entry, directories, e, et, f, commune, dpt, country
        OPTIONAL MATCH (entry:Entry)-[:MEMBER_OF]->(membership:Entry)
        WITH entry, directories, e, et, f, commune, dpt, country, COLLECT(DISTINCT membership) as memberships
        OPTIONAL MATCH (entry:Entry)-[:EMPLOYER]->(employer:Entry)
        WITH entry, directories, e, et, f, commune, dpt, country, memberships, COLLECT(DISTINCT employer) as employers
        OPTIONAL MATCH (entry:Entry)<-[:TAGS]-(tag:Tag)-[IS_A]->(tagcat:TagCategory)<-[:HAS_TAG_CATEGORY]-(et)
        WITH entry, directories, e, et, f, commune, dpt, country, memberships, employers, COLLECT(DISTINCT tag) as tags, COLLECT(DISTINCT tagcat) as tagcats
        RETURN DISTINCT entry.uid as uid, entry, directories, e, et, f, memberships, employers, commune, dpt, country, tags, tagcats;"""
    return query

def sync_get_entries(
        directory: Directory,
        uid = None,
        active: bool = True,
    ):
    query = get_entries_query(directory, uid=uid, active=active)
    results, _meta = db.cypher_query(query, resolve_objects = True)
    #logger.debug(f"{results[:1]=} {len(results)=}")
    entries=[]
    for row in results:
        (
            _,
            entry,
            [directories],
            effector,
            effector_type,
            facility,
            [memberships],
            [employers],
            commune,
            department,
            country,
            [tags],
            [tagcats],
        ) = row
        #logger.debug(f"> {memberships=}")
        #logger.debug(f">> {tags=}")
        #logger.debug(f">>> {tagcats=}")
        address = get_address(facility,commune,country)
        avatar=get_avatar_url(entry=entry)
        memberships_uids = node_uids(memberships) if memberships else []
        #if memberships:
        #    logger.debug(f"********\n-------> {effector.name_fr=} {memberships=}\n********")
        employers = node_uids(employers) if employers else []
        entries.append(
            {
                "effector": effector,
                "entry": entry,
                "address": address,
                "commune": commune,
                "department": department,
                "effector_type": effector_type,
                "facility": facility,
                "avatar": avatar,
                "memberships": memberships_uids,
                "employers": employers,
                "tags": tags,
                "tagcats": tagcats,
                "directories": directories
            }
        )
    return entries

async def get_entries(
        directory: Directory,
        uid = None,
        active: bool = True,
    ):
    query = get_entries_query(directory, uid=uid, active=active)
    results, _meta = await adb.cypher_query(query, resolve_objects = True)
    #logger.debug(f"{results[:1]=} {len(results)=}")
    entries=[]
    for row in results:
        (
            _,
            entry,
            [directories],
            effector,
            effector_type,
            facility,
            [memberships],
            [employers],
            commune,
            department,
            country,
            [tags],
            [tagcats],
        ) = row
        #logger.debug(f"> {memberships=}")
        #logger.debug(f">> {tags=}")
        #logger.debug(f">>> {tagcats=}")
        address = get_address(facility,commune,country)
        avatar = await async_get_avatar_url(entry=entry)
        memberships_uids = node_uids(memberships) if memberships else []
        #if memberships:
        #    logger.debug(f"********\n-------> {effector.name_fr=} {memberships=}\n********")
        employers = node_uids(employers) if employers else []
        entries.append(
            {
                "effector": effector,
                "entry": entry,
                "address": address,
                "commune": commune,
                "department": department,
                "effector_type": effector_type,
                "facility": facility,
                "avatar": avatar,
                "memberships": memberships_uids,
                "employers": employers,
                "tags": tags,
                "tagcats": tagcats,
                "directories": directories
            }
        )
    #logger.debug(f"{len(entries)=}\n{entries[0]=}")
    return entries

def get_location_uids(effector_uids):
    results, cols = db.cypher_query(
        f"""MATCH (e:Effector)-[rel:LOCATION]-(f:Facility)
        WHERE e.uid IN {effector_uids}
        RETURN rel;"""
    )
    if results:
        location_uids=[]
        for row in results:
            location=EffectorFacility.inflate(row[cols.index('rel')])
            location_uids.append(location.uid)
        return location_uids

def entries_of_situation(request, situation):
    entries=[]
    directory=get_directory(request)
    results, _meta = db.cypher_query(
        f"""
        MATCH (s:Situation)
        WHERE s.uid = "{situation.uid}"
        MATCH (et:EffectorType)-[:MANAGES]->(s)
        MATCH (et)<-[:IS_A*]-(:Effector)<-[:HAS_EFFECTOR]-(e:Entry)<-[:HAS_ENTRY]-(d:Directory)
        WHERE d.name = "{directory.name}"
        RETURN e
        """
    )
    if results:
        for e in results:
            entry=Entry.inflate(e[0])
            entries.append(entry)
    results, _meta = db.cypher_query(
        f"""
        MATCH (s:Situation)
        WHERE s.uid = "{situation.uid}"
        MATCH (s)-[:IMPACTS]->(n:Need)<-[:MANAGES]-(et:EffectorType)
        MATCH (et)<-[:IS_A*]-(:Effector)<-[:HAS_EFFECTOR]-(e:Entry)<-[:HAS_ENTRY]-(d:Directory)
        WHERE d.name = "{directory.name}"
        RETURN e
        """
    )
    if results:
        for e in results:
            entry=Entry.inflate(e[0])
            entries.append(entry)
    results, _meta = db.cypher_query(
        f"""
        MATCH (s:Situation)
        WHERE s.uid = "{situation.uid}"
        MATCH (s)-[:IMPACTS]->(n:Need)<-[:PART_OF]-(n2:Need)<-[:MANAGES]-(et:EffectorType)
        MATCH (et)<-[:IS_A*]-(:Effector)<-[:HAS_EFFECTOR]-(e:Entry)<-[:HAS_ENTRY]-(d:Directory)
        WHERE d.name = "{directory.name}"
        RETURN e
        """
    )
    if results:
        for e in results:
            entry=Entry.inflate(e[0])
            entries.append(entry)

    entries_uids = [ e.uid for e in entries]
    return entries_uids

async def async_entries_of_situation(directory, situation):
    entries=[]
    q1=f"""
        MATCH (s:Situation)
        WHERE s.uid = "{situation.uid}"
        MATCH (et:EffectorType)-[:MANAGES]->(s)
        MATCH (et)<-[:IS_A*]-(:Effector)<-[:HAS_EFFECTOR]-(e:Entry)<-[:HAS_ENTRY]-(d:Directory)
        WHERE d.name = "{directory.name}"
        RETURN e
        """
    q2=f"""
        MATCH (s:Situation)
        WHERE s.uid = "{situation.uid}"
        MATCH (s)-[:IMPACTS]->(n:Need)<-[:MANAGES]-(et:EffectorType)
        MATCH (et)<-[:IS_A*]-(:Effector)<-[:HAS_EFFECTOR]-(e:Entry)<-[:HAS_ENTRY]-(d:Directory)
        WHERE d.name = "{directory.name}"
        RETURN e
        """
    q3=f"""
        MATCH (s:Situation)
        WHERE s.uid = "{situation.uid}"
        MATCH (s)-[:IMPACTS]->(n:Need)<-[:PART_OF]-(n2:Need)<-[:MANAGES]-(et:EffectorType)
        MATCH (et)<-[:IS_A*]-(:Effector)<-[:HAS_EFFECTOR]-(e:Entry)<-[:HAS_ENTRY]-(d:Directory)
        WHERE d.name = "{directory.name}"
        RETURN e
        """
    for q in [q1,q2,q3]:
        results, _meta = await adb.cypher_query(q, resolve_objects = True)
        if results:
            for row in results:
                (entry,)=row
                entries.append(entry)
    entries_uids = [e.uid for e in entries]
    return entries_uids

def add_label(uid: str, label: str):
    db.cypher_query(
        f"""MATCH (e)
        WHERE e.uid="{uid}"
        SET e :{label}
        RETURN e;"""
    )

def find_effector_uid(effector_type_slug, commune_slug, effector_slug):
    results, cols = db.cypher_query(
        f"""MATCH (et:EffectorType)<-[:IS_A]-(e:Effector)-[rel:LOCATION]->(f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)
        WHERE e.slug_fr="{effector_slug}" AND c.slug_fr="{commune_slug}" AND et.slug_fr="{effector_type_slug}"
        RETURN rel;"""
    )
    #effectors=[]
    uids=[]
    if results:
        for row in results:
            #effector=Effector.inflate(row[cols.index('e')])
            #effectors.append(effector)
            location=EffectorFacility.inflate(row[cols.index('rel')])
            uids.append(location.uid)
    try:
        return uids[0]
    except Exception as e:
        logger.error(
            f"No Location relationship with {effector_type_slug=}, {commune_slug=}, "
            f"{effector_slug=} could be found. {e}"
        )

def get_uid_query(uid: str):
    return f"""
        MATCH (entry:Entry)-[:HAS_FACILITY]->(f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY*]->(country:Country),
        (entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType),
        (entry)-[:HAS_EFFECTOR]->(e:Effector)
        WHERE entry.uid="{uid}"
        OPTIONAL MATCH (entry)-[:MEMBER_OF]->(memberships:Entry)
        WITH *, COLLECT(memberships) AS memberships
        OPTIONAL MATCH (e:Effector)-[rel:LOCATION]->(f:Facility)
        WITH *
        OPTIONAL MATCH (tpp:ThirdPartyPayer) WHERE tpp.name IN entry.third_party_payer
        WITH *, COLLECT(tpp) AS tpp
        OPTIONAL MATCH (pm:PaymentMethod) WHERE pm.name IN entry.payment
        WITH *, COLLECT(pm) AS pm
        OPTIONAL MATCH (convention:Convention) WHERE convention.name=entry.convention
        OPTIONAL MATCH (entry)-[:HAS_APPOINTMENT]->(a:Appointment)
        WITH *, COLLECT(DISTINCT a) AS a
        MATCH (et)-[:IS_A*0..]->(b:EffectorType)
        WITH *, et, collect(DISTINCT labels(b)) AS bLabels
        WITH *, bLabels + labels(et) AS allLabels
        UNWIND allLabels AS labelList
        UNWIND labelList AS label
        WITH entry,et,e,rel,f,c,country,tpp,pm,convention,a,COLLECT(DISTINCT label) AS effector_type_labels,memberships
        OPTIONAL MATCH (entry:Entry)<-[:TAGS]-(tag:Tag)-[IS_A]->(tagcat:TagCategory)<-[:HAS_TAG_CATEGORY]-(et)
        WITH entry,et,e,rel,f,c,country,tpp,pm,convention,a, effector_type_labels,memberships, COLLECT(DISTINCT tag) as tags, COLLECT(DISTINCT tagcat) as tagcats
        MATCH (entry)<-[:HAS_ENTRY]-(directory:Directory)
        WITH entry,et,e,rel,f,c,country,tpp,pm,convention,a, effector_type_labels,memberships, tags, tagcats, COLLECT(DISTINCT directory) as directories
        RETURN entry,et,e,rel,f,c,country,tpp,pm,convention,a,effector_type_labels,memberships,tags,tagcats,directories;"""

def get_slug_query(directory, effector_slug, effector_type_slug, facility_slug):
    return f"""MATCH (d:Directory) WHERE d.name="{directory.name}"
        WITH d
        MATCH (d)-[:HAS_ENTRY]->(entry:Entry)
        WITH entry
        MATCH (entry)-[:HAS_FACILITY]->(f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY*]->(country:Country),
        (entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType),
        (entry)-[:HAS_EFFECTOR]->(e:Effector)
        WHERE e.slug_fr="{effector_slug}"
        AND f.slug="{facility_slug}"
        AND et.slug_fr="{effector_type_slug}"
        OPTIONAL MATCH (entry)-[:MEMBER_OF]->(memberships:Entry)
        WITH *, COLLECT(memberships) AS memberships
        OPTIONAL MATCH (e:Effector)-[rel:LOCATION]->(f:Facility)
        WITH *
        OPTIONAL MATCH (tpp:ThirdPartyPayer) WHERE tpp.name IN entry.third_party_payer
        WITH *, COLLECT(tpp) AS tpp
        OPTIONAL MATCH (pm:PaymentMethod) WHERE pm.name IN entry.payment
        OPTIONAL MATCH (convention:Convention) WHERE convention.name=entry.convention
        OPTIONAL MATCH (entry)-[:HAS_APPOINTMENT]->(a:Appointment)
        WITH *, COLLECT(DISTINCT a) AS a
        MATCH (et)-[:IS_A*0..]->(b:EffectorType)
        WITH *, et, collect(DISTINCT labels(b)) AS bLabels
        WITH *, bLabels + labels(et) AS allLabels
        UNWIND allLabels AS labelList
        UNWIND labelList AS label
        WITH entry,et,e,rel,f,c,country,tpp,pm,convention,a,COLLECT(DISTINCT label) AS effector_type_labels,memberships
        OPTIONAL MATCH (entry:Entry)<-[:TAGS]-(tag:Tag)-[IS_A]->(tagcat:TagCategory)<-[:HAS_TAG_CATEGORY]-(et)
        WITH entry,et,e,rel,f,c,country,tpp,pm,convention,a, effector_type_labels,memberships, COLLECT(DISTINCT tag) as tags, COLLECT(DISTINCT tagcat) as tagcats
        MATCH (entry)<-[:HAS_ENTRY]-(directory:Directory)
        WITH entry,et,e,rel,f,c,country,tpp,pm,convention,a, effector_type_labels,memberships, tags, tagcats, COLLECT(DISTINCT directory) as directories
        RETURN entry,et,e,rel,f,c,country,tpp,pm,convention,a,effector_type_labels,memberships,tags,tagcats,directories;"""

def entry_dict(results, cols):
    #logger.debug(f"{results[:1]=} {len(results)=}")
    try:
        row=results[0]
    except Exception as e:
        logger.error(e)
        return
    #logger.debug(f"{row=} {len(row)=}")
    [
        entry,
        effector_type,
        effector,
        effector_facility,
        facility,
        commune,
        country,
        [third_party_payers],
        [payment_methods],
        convention,
        [appointment_nodes],
        [effector_type_labels],
        [memberships],
        [tags],
        [tagcats],
        [directories],
    ] = row
    #logger.debug(f"{entry=}")
    #logger.debug(f"{appointment_nodes=}")
    #logger.debug(f"{third_party_payers=}")
    #logger.debug(f"{effector_type_labels=}")
    address = get_address(facility,commune,country)
    phones = get_phones_neomodel(entry=entry)
    emails = get_emails_neomodel(
        entry=entry,
        e=effector,
        ef=effector_facility,
        f=facility
    )
    websites = get_websites_neomodel(
        entry=entry,
        e=effector,
        ef=effector_facility,
        f=facility
    )
    socialnetworks = get_socialnetworks_neomodel(
        entry=entry,
        e=effector,
        ef=effector_facility,
        f=facility
    )
    appointments = appointments_from_neomodel(
        entry=entry.uid,
        nodes=appointment_nodes
    )
    profile = get_profile_neomodel(
        entry=entry,
        e=effector,
        ef=effector_facility,
        f=facility
    )
    try:
        health_worker = HealthWorker.nodes.get(uid=effector.uid)
    except Exception as e:
        logger.warning(e)
        health_worker = None
    avatar=get_avatar_url(entry, effector, effector_facility, facility)
    fetl=flex_effector_type_label(effector, effector_type)
    directories=[d.name for d in directories]
    return {
        "entry": entry,
        "effector": effector,
        "location": effector_facility,
        "address": address,
        #"commune": commune,
        "effector_type": effector_type,
        "flex_effector_type_label": fetl,
        "effector_type_labels": effector_type_labels,
        "facility": facility,
        "phones": phones,
        "emails": emails,
        "websites": websites,
        "socialnetworks": socialnetworks,
        "appointments": appointments,
        "profile": profile,
        "third_party_payers": third_party_payers,
        "payment_methods": payment_methods,
        "health_worker": health_worker,
        "avatar": avatar,
        "convention": convention,
        "memberships": memberships,
        "tags": tags,
        "tagcats": tagcats,
        "directories": directories,
    }

async def async_entry_dict(results, cols):
    try:
        row=results[0]
    except Exception as e:
        logger.error(e)
        return
    entry=Entry.inflate(row[cols.index('entry')])
    effector=Effector.inflate(row[cols.index('e')])
    try:
        effector_facility=EffectorFacility.inflate(row[cols.index('rel')])
    except Exception as e:
        effector_facility=None
    facility=Facility.inflate(row[cols.index('f')])
    commune=Commune.inflate(row[cols.index('c')])
    country=Country.inflate(row[cols.index('country')])
    effector_type=EffectorType.inflate(row[cols.index('et')])
    address = get_address(facility,commune,country)
    a=row[cols.index('a')]
    if a and isinstance(a, list) and len(a) and a[0]:
        appointment_nodes = [Appointment.inflate(node) for node in a]
    elif a and not isinstance(a,list):
        try:
            appointment_nodes = [Appointment.inflate(a)]
        except Exception as e:
            logger.error(e)
            appointment_nodes = None
    else:
        appointment_nodes = None
    phones = await async_get_phones_neomodel(entry=entry)
    emails = await async_get_emails_neomodel(
        entry=entry,
        e=effector,
        ef=effector_facility,
        f=facility
    )
    websites = await async_get_websites_neomodel(entry)
    socialnetworks = await async_get_socialnetworks_neomodel(
        entry=entry,
        facility=facility
    )
    appointments = appointments_from_neomodel(
        entry=entry.uid,
        nodes=appointment_nodes
    )
    profile = await async_get_profile_neomodel(
        entry=entry,
        e=effector,
        ef=effector_facility,
        f=facility
    )
    try:
        third_party_payers = [
            ThirdPartyPayer.inflate(payer)
            for payer in row[cols.index('tpp')]
        ]
    except:    
        third_party_payers = None
    payment_methods = [
        PaymentMethod.inflate(pm)
        for pm in row[cols.index('pm')]
    ] or None
    try:
        convention =  Convention.inflate(row[cols.index('convention')])
    except:
        convention = None
    memberships = [
        Entry.inflate(e)
        for e in row[cols.index('memberships')]
    ] or None
    health_worker=HealthWorker.inflate(row[cols.index('e')])
    avatar= await async_get_avatar_url(entry, effector, effector_facility, facility)
    fetl= await async_flex_effector_type_label(effector, effector_type)
    tags = [
            Tag.inflate(tag)
            for tag in row[cols.index('tags')]
        ] or None
    directories=[
            GraphDirectory.inflate(d)
            for d in row[cols.index('directories')]
        ] or None
    return {
        "entry": entry,
        "effector": effector,
        "location": effector_facility,
        "address": address,
        #"commune": commune,
        "effector_type": effector_type,
        "flex_effector_type_label": fetl,
        "effector_type_labels": row[cols.index('effector_type_labels')],
        "facility": facility,
        "phones": phones,
        "emails": emails,
        "websites": websites,
        "socialnetworks": socialnetworks,
        "appointments": appointments,
        "profile": profile,
        "third_party_payers": third_party_payers,
        "payment_methods": payment_methods,
        "health_worker": health_worker,
        "avatar": avatar,
        "convention": convention,
        "memberships": memberships,
        "tags": tags,
        "directories": directories,
    }

def find_entry(
        directory: Directory|None = None,
        facility_slug: str|None = None,
        effector_type_slug: str|None = None,
        effector_slug: str|None = None,
        uid: str|None = None,
    ):
    if uid:
        query = get_uid_query(uid)
    else:
        query= get_slug_query(directory, effector_slug, effector_type_slug, facility_slug)
    results, cols = db.cypher_query(query, resolve_objects=True)
    return entry_dict(results, cols)

async def async_find_entry(
        directory: Directory|None = None,
        facility_slug: str|None = None,
        effector_type_slug: str|None = None,
        effector_slug: str|None = None,
        uid: str|None = None,
    ):
    if uid:
        query = get_uid_query(uid)
    else:
        query= get_slug_query(directory, effector_slug, effector_type_slug, facility_slug)
    results, cols = await adb.cypher_query(query)
    return await async_entry_dict(results, cols)

def effector_types(directory: Directory) -> list[str]:
    query=f"""MATCH (et:EffectorType)<-[:IS_A]-(e:Effector)-[rel:LOCATION]->(f:Facility)
        WHERE rel.directories=["{directory.name}"] AND rel.active = true
        RETURN COLLECT(et.uid) AS uids;"""
    results, cols = db.cypher_query(query)
    uids1=results[0][cols.index('uids')]
    query=f"""MATCH (d:Directory)
        WHERE d.name="{directory.name}"
        WITH d
        MATCH (d)-[:HAS_ENTRY]->(e:Entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType)
        WHERE e.active = true
        RETURN COLLECT(et.uid) AS uids;"""
    results, cols = db.cypher_query(query)
    uids2=results[0][cols.index('uids')]
    uids = list(set(uids1 + uids2))
    return uids

