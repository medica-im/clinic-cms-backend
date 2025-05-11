import logging
from django.contrib.sites.shortcuts import get_current_site
from directory.models import (
    Directory,
    Effector,
    CareHome,
    EffectorType,
    Facility,
    EffectorFacility,
    Commune,
    ThirdPartyPayer,
    PaymentMethod,
    HealthWorker,
    Entry,
    Organization,
)
from addressbook.models import Contact
from neomodel import db
from addressbook.api.serializers import (
    PhoneNumberSerializer,
    EmailSerializer,
    WebsiteSerializer,
    SocialNetworkSerializer,
    AppointmentSerializer,
    AddressSerializer,
    ProfileSerializer,
)
from access.utils import get_role
from rest_framework.serializers import ModelSerializer
from rdflib.plugins.shared.jsonld.keys import NONE

logger = logging.getLogger(__name__)

def get_directory(request):
    site = get_current_site(request)
    try:
        return Directory.objects.get(site=site)
    except Directory.DoesNotExist:
        return

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

def get_contact_related_neomodel(
        e: Effector|None = None,
        ef: EffectorFacility|None = None,
        f: Facility|None = None,
        attribute: str = "",
        Serializer:  ModelSerializer = None,
        many: bool = True,
        first_hit = False,
    ):
    elements = set()
    for neo_entity in [e, ef, f]:
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

def get_profile_neomodel(e: Effector, ef: EffectorFacility, f: Facility):
    return get_contact_related_neomodel(
        e=e,
        ef=ef,
        f=f,
        attribute="profile",
        Serializer=ProfileSerializer,
        many=False
    )

def get_appointments_neomodel(e: Effector, ef: EffectorFacility, f: Facility):
    return get_contact_related_neomodel(
        e=e,
        ef=ef,
        f=f,
        attribute="appointments",
        Serializer=AppointmentSerializer
)

def get_websites_neomodel(
        e: Effector | None = None,
        ef: EffectorFacility | None = None,
        f: Facility | None = None
    ):
    return get_contact_related_neomodel(
        e=e,
        ef=ef,
        f=f,
        attribute="websites",
        Serializer=WebsiteSerializer
    )

def get_socialnetworks_neomodel(
        e: Effector | None = None,
        ef: EffectorFacility | None = None,
        f: Facility | None = None,
    ):
    return get_contact_related_neomodel(
        e=e,
        ef=ef,
        f=f,
        attribute="socialnetworks",
        Serializer=SocialNetworkSerializer
    )

def get_phones_neomodel(
        e: Effector | None = None,
        ef: EffectorFacility | None = None,
        f: Facility | None = None,
    ):
    return get_contact_related_neomodel(
        e=e,
        ef=ef,
        f=f,
        attribute="phonenumbers",
        Serializer=PhoneNumberSerializer,
        first_hit=True,
        many=True,
    )

def get_emails_neomodel(
        e: Effector | None = None,
        ef: EffectorFacility | None = None,
        f: Facility | None = None
    ):
    return get_contact_related_neomodel(
        e=e,
        ef=ef,
        f=f,
        attribute="emails",
        Serializer=EmailSerializer,
        first_hit=False,
        many=True,
    )

def get_phones(request, effector):
    directory=get_directory(request)
    results, cols = db.cypher_query(
        f"""MATCH (e:Effector)-[rel:LOCATION]-(f:Facility)
        WHERE rel.directories=["{directory.name}"]
        AND e.uid="{effector.uid}"
        RETURN f, rel"""
    )
    if results:
        location_facility = []
        for row in results:
            _dct = {}
            location_rel=EffectorFacility.inflate(row[cols.index('rel')])
            _dct["location_rel"]=location_rel
            facility=Facility.inflate(row[cols.index('f')])
            _dct["facility"]=facility
            location_facility.append(_dct)
        phones = []
        for lf in location_facility:
            try:
                contact = Contact.objects.get(neomodel_uid=lf["location_rel"].uid)
            except Contact.DoesNotExist:
                contact = None
            if not (contact and contact.phonenumbers.all()):
                try:
                    contact = Contact.objects.get(neomodel_uid=lf["facility"].uid)
                except Contact.DoesNotExist:
                    continue
            role = get_role(request)
            _phones = contact.phonenumbers.filter(roles__in=[role]).distinct()
            serializer = PhoneNumberSerializer(
                _phones,
                many=True
            )
            phones.extend(serializer.data)
        return phones

def get_avatar_url(
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
        e_avatar = Contact.objects.get(neomodel_uid=e.uid).profile_image
    except (Contact.DoesNotExist, AttributeError):
        e_avatar = None
    try:
        ef_avatar = Contact.objects.get(neomodel_uid=ef.uid).profile_image
    except (Contact.DoesNotExist, AttributeError):
        ef_avatar = None
    try:
        f_avatar = Contact.objects.get(neomodel_uid=f.uid).profile_image
    except (Contact.DoesNotExist, AttributeError):
        f_avatar = None
    if (e_avatar and ef_avatar):
        return get_avatar_dict(ef_avatar)
    if (not ef_avatar and e_avatar):
        return get_avatar_dict(e_avatar)
    if (ef_avatar):
        return get_avatar_dict(ef_avatar)
    if (e is None and ef is None and f):
        return get_avatar_dict(f_avatar)

def get_address(facility: Facility):
    try:
        contact = Contact.objects.get(neomodel_uid=facility.uid)
    except Contact.DoesNotExist:
        return
    serializer = AddressSerializer(contact.address)
    return serializer.data

def org_uids(orgs):
    try:
        return [org.uid for org in orgs]
    except Exception as e:
        logger.debug(e)
        try:
            return [orgs.uid]
        except Exception as e:
            logger.debug(e)
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
        uid = None,
        label: str = "Effector",
        active: bool = True,
    ):
    if uid:
        query=f"""MATCH (e:{label})-[rel:LOCATION]-(f:Facility)
        WHERE f.uid="{uid}"
        RETURN f;"""
    else:
        query=f"""MATCH (d:Directory)-[:HAS_ENTRY]->(e:Entry),
        (e)-[:HAS_EFFECTOR]->(:Effector),
        (e)-[:HAS_FACILITY]->(f:Facility)
        WHERE d.name="{directory.name}"
        AND e.active={str(active)}
        RETURN DISTINCT f;"""
    results, cols = db.cypher_query(query)
    _facilities=[]
    try:
        for row in results:
            _facilities.append(
                Facility.inflate(row[cols.index('f')])
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
        query=f"""MATCH (et:EffectorType)<-[:IS_A]-(e:{label})-[rel:LOCATION]-(f:Facility)-[]->(c:Commune)
        WHERE rel.directories=["{directory.name}"] AND (rel.uid="{uid}")
        RETURN e,et,rel,f,c;"""
    else:
        query=f"""MATCH (et:EffectorType)<-[:IS_A]-(e:{label})-[rel:LOCATION]-(f:Facility)-[]->(c:Commune)
        WHERE rel.directories=["{directory.name}"] AND rel.active={str(active)}
        RETURN e,et,rel,f,c;"""
    results, cols = db.cypher_query(query)
    if results:
        effectors=[]
        for row in results:
            effector=Effector.inflate(row[cols.index('e')])
            location=EffectorFacility.inflate(row[cols.index('rel')])
            facility=Facility.inflate(row[cols.index('f')])
            commune=Commune.inflate(row[cols.index('c')])
            types=EffectorType.inflate(row[cols.index('et')])
            types = types if isinstance(types, list) else [types]
            address = get_address(facility)
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

def get_entries(
        directory: Directory,
        uid = None,
        label: str = "Effector",
        active: bool = True,
    ):
    if uid:
        query=f"""
        MATCH (entry:Entry) WHERE entry.uid="{uid}"
        WITH entry
        MATCH (entry)-[:HAS_FACILITY]->(f:Facility)-[]->(commune:Commune)
        MATCH (entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType)
        MATCH (entry)-[:HAS_EFFECTOR]->(e:Effector)
        WITH *
        MATCH (e:Effector)-[rel:LOCATION]-(f:Facility)
        OPTIONAL MATCH (entry:Entry)-[:MEMBER_OF]->(o:Organization)
        OPTIONAL MATCH (entry:Entry)-[:EMPLOYER]->(employer:Organization)
        RETURN entry,e,et,f,rel,o,employer,commune;
        """
    else:
        query=f"""
        MATCH (d:Directory) WHERE d.name="{directory.name}"
        WITH d
        MATCH (d)-[:HAS_ENTRY]->(entry:Entry) WHERE entry.active={str(active)}
        WITH entry
        MATCH (entry)-[:HAS_FACILITY]->(f:Facility)-[]->(commune:Commune)
        MATCH (entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType)
        MATCH (entry)-[:HAS_EFFECTOR]->(e:Effector)
        WITH *
        MATCH (e:Effector)-[rel:LOCATION]-(f:Facility)
        OPTIONAL MATCH (entry:Entry)-[:MEMBER_OF]->(o:Organization)
        OPTIONAL MATCH (entry:Entry)-[:EMPLOYER]->(employer:Organization)
        RETURN entry,e,et,f,rel,o,employer,commune;
        """
    q = db.cypher_query(query,resolve_objects = True)
    logger.debug(f'{display(q[0][0])}')
    logger.debug(f'****************************\nq:\n{len(q[0][0])}')
    logger.debug(f'****************************\nq:\n{q[0][0][0].__properties__}')
    if q:
        entries=[]
        for row in q[0]:
            logger.debug(len(row))
            logger.debug(row)
            (
                entry,
                effector,
                effector_type,
                facility,
                location,
                organizations,
                employers,
                commune
            )= row
            address = get_address(facility)
            avatar=get_avatar_url(effector, location, facility)
            entries.append(
                {
                    "effector": effector,
                    "entry": entry,
                    "address": address,
                    "commune": commune,
                    "effector_type": effector_type,
                    "facility": facility,
                    "avatar": avatar,
                    "location": location,
                    "organizations": org_uids(organizations),
                    "employers": org_uids(employers),
                }
            )
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

def add_label(uid: str, label: str):
    results, cols = db.cypher_query(
        f"""MATCH (e)
        WHERE e.uid="{uid}"
        SET e :{label}
        RETURN e;"""
    )
    node=None
    if results:
        for row in results:
            node=row[cols.index('e')]
    if node:
        logger.debug(f"Label {label} added to node {node}")
    else:
        logger.error(f"No node with uid={uid} could be found.")
        
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
        
        
def find_entry(
        directory: Directory,
        facility_slug: str,
        effector_type_slug: str,
        effector_slug: str
    ):
    query=(
        f"""
        MATCH (d:Directory) WHERE d.name="{directory.name}"
        WITH d
        MATCH (d)-[:HAS_ENTRY]->(entry:Entry)
        WITH entry
        MATCH (entry)-[:HAS_FACILITY]->(f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune),
        (entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType),
        (entry)-[:HAS_EFFECTOR]->(e:Effector)
        WHERE e.slug_fr="{effector_slug}"
        AND f.slug="{facility_slug}"
        AND et.slug_fr="{effector_type_slug}"
        WITH *
        MATCH (e:Effector)-[rel:LOCATION]->(f:Facility)
        WITH *
        OPTIONAL MATCH (tpp:ThirdPartyPayer) WHERE tpp.name IN rel.thirdPartyPayment
        WITH *, COLLECT(tpp) AS tpp
        OPTIONAL MATCH (pm:PaymentMethod) WHERE pm.name IN rel.payment
        RETURN et,e,rel,f,c,tpp,COLLECT(pm) AS pm;
        """
    )
    results, cols = db.cypher_query(query)
    try:
        row=results[0]
    except Exception as e:
        logger.error(e)
        return
    effector=Effector.inflate(row[cols.index('e')])
    effector_facility=EffectorFacility.inflate(row[cols.index('rel')])
    facility=Facility.inflate(row[cols.index('f')])
    #commune=Commune.inflate(row[cols.index('c')])
    effector_type=EffectorType.inflate(row[cols.index('et')])
    address = get_address(facility)
    phones = get_phones_neomodel(
        e=effector,
        ef=effector_facility,
        f=facility
    )
    emails = get_emails_neomodel(
        e=effector,
        ef=effector_facility,
        f=facility
    )
    websites = get_websites_neomodel(
        e=effector,
        ef=effector_facility,
        f=facility
    )
    socialnetworks = get_socialnetworks_neomodel(
        e=effector,
        ef=effector_facility,
        f=facility
    )
    appointments = get_appointments_neomodel(
        e=effector,
        ef=effector_facility,
        f=facility
    )
    profile = get_profile_neomodel(
        e=effector,
        ef=effector_facility,
        f=facility
    )
    third_party_payers = [
        ThirdPartyPayer.inflate(payer)
        for payer in row[cols.index('tpp')]
    ]
    payment_methods = [
        PaymentMethod.inflate(pm)
        for pm in row[cols.index('pm')]
    ]
    health_worker=HealthWorker.inflate(row[cols.index('e')])
    avatar=get_avatar_url(effector, effector_facility, facility)
    return {
        "effector": effector,
        "location": effector_facility,
        "address": address,
        #"commune": commune,
        "effector_type": effector_type,
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
        "avatar": avatar
    }

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