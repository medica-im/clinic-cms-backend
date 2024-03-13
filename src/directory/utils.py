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
from workforce.serializers import ConventionSerializer
from rest_framework.serializers import ModelSerializer

logger = logging.getLogger(__name__)

def get_directory(request):
    site = get_current_site(request)
    try:
        return Directory.objects.get(site=site)
    except Directory.DoesNotExist:
        return

def get_contact_related_neomodel(
        ef: EffectorFacility,
        f: Facility,
        attribute: str,
        Serializer:  ModelSerializer,
        many: bool = True
    ):
    try:
        contact = Contact.objects.get(neomodel_uid=ef.uid)
    except Contact.DoesNotExist:
        contact = None
    try:
        related = getattr(contact, attribute)
        if many:
            has_related = bool(related.all())
        else:
            has_related = bool(related)
    except AttributeError:
        has_related = False
    if not contact or not has_related:
        try:
            contact = Contact.objects.get(neomodel_uid=f.uid)
        except Contact.DoesNotExist:
            return
    try:
        if many:
            elements = getattr(contact, attribute).all()
        else:
            elements = getattr(contact, attribute)
    except AttributeError:
        return
    logger.debug(f'{elements=}')
    serializer = Serializer(
        elements,
        many=many
    )
    return serializer.data

def get_profile_neomodel(ef: EffectorFacility, f: Facility):
    return get_contact_related_neomodel(
        ef,
        f,
        "profile",
        ProfileSerializer,
        many=False
    )

def get_appointments_neomodel(ef: EffectorFacility, f: Facility):
    return get_contact_related_neomodel(
        ef,
        f,
        "appointments",
        AppointmentSerializer
)

def get_websites_neomodel(ef: EffectorFacility, f: Facility):
    return get_contact_related_neomodel(
        ef,
        f,
        "websites",
        WebsiteSerializer
    )

def get_socialnetworks_neomodel(ef: EffectorFacility, f: Facility):
    return get_contact_related_neomodel(
        ef,
        f,
        "socialnetworks",
        SocialNetworkSerializer
    )

def get_phones_neomodel(ef: EffectorFacility, f: Facility):
    phones = []
    try:
        contact = Contact.objects.get(neomodel_uid=ef.uid)
    except Contact.DoesNotExist:
        contact = None
    if not contact or not contact.phonenumbers.all():
        try:
            contact = Contact.objects.get(neomodel_uid=f.uid)
        except Contact.DoesNotExist:
            return
    serializer = PhoneNumberSerializer(
        contact.phonenumbers.all(),
        many=True
    )
    phones.extend(serializer.data)
    return phones

def get_emails_neomodel(ef: EffectorFacility, f: Facility):
    emails = []
    try:
        contact = Contact.objects.get(neomodel_uid=ef.uid)
        logger.debug(f'{contact=} {contact.emails.all()=}')
    except Contact.DoesNotExist:
        contact = None
    if not contact or not contact.emails.all():
        try:
            contact = Contact.objects.get(neomodel_uid=f.uid)
        except Contact.DoesNotExist:
            return
    serializer = EmailSerializer(
        contact.emails.all(),
        many=True
    )
    emails.extend(serializer.data)
    return emails

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

def get_avatar_url(effector_facility_uid):
    try:
        contact = Contact.objects.get(neomodel_uid=effector_facility_uid)
    except Contact.DoesNotExist:
        return
    try:
        fb = contact.profile_image["avatar_facebook"].url
        logger.debug(f'{fb=}')
    except:
        fb = None
    try:
        lt = contact.profile_image["avatar_linkedin_twitter"].url
        logger.debug(f'{lt=}')
    except:
        lt = None
    return {
        "fb": fb,
        "lt": lt
    }

def get_address(facility: Facility):
    try:
        contact = Contact.objects.get(neomodel_uid=facility.uid)
    except Contact.DoesNotExist:
        return
    serializer = AddressSerializer(contact.address)
    return serializer.data

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
        query=f"""MATCH (e:{label})-[rel:LOCATION]-(f:Facility)
        WHERE rel.directories=["{directory.name}"] AND rel.active={str(active)}
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
        query=f"""MATCH (e:{label})-[rel:LOCATION]-(f:Facility)
        WHERE rel.directories=["{directory.name}"] AND (rel.uid="{uid}")
        RETURN e,rel,f;"""
    else:
        query=f"""MATCH (e:{label})-[rel:LOCATION]-(f:Facility)
        WHERE rel.directories=["{directory.name}"] AND rel.active={str(active)}
        RETURN e,rel,f;"""
    results, cols = db.cypher_query(query)
    contacts=[]
    if results:
        for row in results:
            effector=row[cols.index('e')]
            location=row[cols.index('rel')]
            facility=row[cols.index('f')]
            """
            logger.debug(
                f'{effector=} {effector["updatedAt"]=} {effector.__dict__=}\n'
                f'{location=} {location.__dict__}\n'
                f'{facility=} {facility.__dict__=}'
            )
            """
            timestamp = max(
                [
                    effector["updatedAt"],
                    location["contactUpdatedAt"],
                    facility["contactUpdatedAt"]
                ]
            )
            contacts.append(
                {
                    "uid": location["uid"],
                    "timestamp": timestamp
                }
            )
    return contacts


def contact_uids(directory: Directory=None, active=True, search=""):
    directory_query = ""
    if directory:
        directory_query=f'AND rel.directories=["{directory.name}"]'
    search_query = ""
    if search:
        search_query = f'AND n.name_fr =~ "(?i).*{search}.*"'
    query=f"""MATCH (n)-[rel:LOCATION]-(f:Facility)
        WHERE (n:Effector OR n:Organization)
        {directory_query}
        AND rel.active={str(active)}
        {search_query}
        RETURN rel,f;"""
    logger.warn(query)
    results, cols = db.cypher_query(query)
    if results:
        contacts=[]
        for row in results:
            location=EffectorFacility.inflate(row[cols.index('rel')])
            facility=Facility.inflate(row[cols.index('f')])
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
            effectors.append(
                {
                    "effector": effector,
                    "location": location,
                    "address": address,
                    "commune": commune,
                    "types": types,
                    "facility": facility,
                }
            )
        return effectors

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

def get_effectors(request, situation):
    effectors=[]
    directory=get_directory(request)
    results, meta = db.cypher_query(
        f"""
        MATCH (s:Situation)
        WHERE s.uid = "{situation.uid}"
        MATCH (et:EffectorType)-[:MANAGES]->(s)
        MATCH (et)<-[:IS_A*]-(e:Effector) RETURN e
        """
    )
    if results:
        for e in results:
            effector=Effector.inflate(e[0])
            effectors.append(effector)
    results, meta = db.cypher_query(
        f"""
        MATCH (s:Situation)
        WHERE s.uid = "{situation.uid}"
        MATCH (s)-[:IMPACTS]->(n:Need)<-[:MANAGES]-(et:EffectorType)
        MATCH (et)<-[:IS_A*]-(e:Effector) RETURN e
        """
    )
    if results:
        for e in results:
            effector=Effector.inflate(e[0])
            effectors.append(effector)
    results, meta = db.cypher_query(
        f"""
        MATCH (s:Situation)
        WHERE s.uid = "{situation.uid}"
        MATCH (s)-[:IMPACTS]->(n:Need)<-[:PART_OF]-(n2:Need)<-[:MANAGES]-(et:EffectorType)
        MATCH (et)<-[:IS_A*]-(e:Effector) RETURN e
        """
    )
    if results:
        for e in results:
            effector=Effector.inflate(e[0])
            effectors.append(effector)
    try:
        _directory_effectors = [
            _dict["effector"] for _dict in directory_effectors(directory)
        ]
    except TypeError:
        return []
    effector_uids = [ e.uid for e in effectors if e in _directory_effectors]
    return get_location_uids(effector_uids)

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
        #logger.debug(f"{effectors[0].uid=}")
        logger.debug(f"{uids[0]=}")
        return uids[0]
    except Exception as e:
        logger.error(
            f"No Location relationship with {effector_type_slug=}, {commune_slug=}, "
            f"{effector_slug=} could be found."
        )
        
        
def find_effector(
        directory: Directory,
        effector_type_slug: str,
        commune_slug: str,
        effector_slug: str
    ):
    query=f"""MATCH (et:EffectorType)<-[:IS_A]-(e:Effector)-[rel:LOCATION]->(f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)
        WHERE e.slug_fr="{effector_slug}" AND c.slug_fr="{commune_slug}" AND et.slug_fr="{effector_type_slug}" AND rel.directories=["{directory.name}"]
        WITH *
        OPTIONAL MATCH (tpp:ThirdPartyPayer) WHERE tpp.name IN rel.thirdPartyPayment
        WITH *, COLLECT(tpp) AS tpp
        OPTIONAL MATCH (pm:PaymentMethod) WHERE pm.name IN rel.payment
        RETURN et,e,rel,f,c,tpp,COLLECT(pm) AS pm;"""
    logger.debug(query)
    results, cols = db.cypher_query(query)
    logger.debug(results)
    try:
        row=results[0]
    except Exception as e:
        logger.error(e)
        return
    effector=Effector.inflate(row[cols.index('e')])
    effector_facility=EffectorFacility.inflate(row[cols.index('rel')])
    facility=Facility.inflate(row[cols.index('f')])
    commune=Commune.inflate(row[cols.index('c')])
    effector_type=EffectorType.inflate(row[cols.index('et')])
    address = get_address(facility)
    phones = get_phones_neomodel(effector_facility,facility)
    emails = get_emails_neomodel(effector_facility,facility)
    websites = get_websites_neomodel(effector_facility, facility)
    socialnetworks = get_socialnetworks_neomodel(effector_facility, facility)
    appointments = get_appointments_neomodel(effector_facility, facility)
    profile = get_profile_neomodel(effector_facility, facility)
    third_party_payers = [
        ThirdPartyPayer.inflate(payer)
        for payer in row[cols.index('tpp')]
    ]
    payment_methods = [
        PaymentMethod.inflate(pm)
        for pm in row[cols.index('pm')]
    ]
    health_worker=HealthWorker.inflate(row[cols.index('e')])
    avatar=get_avatar_url(effector_facility.uid)
    return {
        "effector": effector,
        "location": effector_facility,
        "address": address,
        "commune": commune,
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