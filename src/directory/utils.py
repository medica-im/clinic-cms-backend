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
)
from addressbook.models import Contact
from neomodel import db
from addressbook.serializers import (
    AddressSerializer,
    PhoneNumberSerializer,
)

logger = logging.getLogger(__name__)

def get_directory(request):
    site = get_current_site(request)
    try:
        dir = Directory.objects.get(site=site)
        return dir
    except Directory.DoesNotExist:
        return

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
                logger.debug(contact);
            except Contact.DoesNotExist:
                contact = None
            if not (contact and contact.phonenumbers.all()):
                try:
                    contact = Contact.objects.get(neomodel_uid=lf["facility"].uid)
                    logger.debug(contact);
                except Contact.DoesNotExist:
                    continue
            serializer = PhoneNumberSerializer(
                contact.phonenumbers.all(),
                many=True
            )
            phones.extend(serializer.data)
        return phones

def get_address(facility):
    try:
        contact = Contact.objects.get(neomodel_uid=facility.uid)
    except Contact.DoesNotExist:
        return
    serializer = AddressSerializer(contact.address)
    return serializer.data

def effector_commune(directory: Directory): 
    results, meta = db.cypher_query(
            f"""MATCH (e:Effector)-[l:LOCATION]-(f:Facility)
            WHERE l.directories=["{directory.name}"]
            RETURN e"""
        )
    if results:
        effectors=[]
        for e in results:
            effector=Effector.inflate(e[0])
            effectors.append(effector)
        return effectors

def get_effector_nodes(directory: Directory, label: str):
    results, cols = db.cypher_query(
        f"""MATCH (e:{label})-[rel:LOCATION]-(f:Facility)
        WHERE rel.directories=["{directory.name}"]
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

def directory_effectors(directory: Directory, label: str = "Effector"): 
    results, cols = db.cypher_query(
        f"""MATCH (et:EffectorType)<-[:IS_A]-(e:{label})-[rel:LOCATION]-(f:Facility)-[]->(c:Commune)
        WHERE rel.directories=["{directory.name}"]
        RETURN e,et,rel,f,c;"""
    )
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
                    "types": types
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
    _directory_effectors = [_dict["effector"] for _dict in directory_effectors(directory)]
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