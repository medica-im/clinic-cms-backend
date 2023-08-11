import logging
from django.contrib.sites.shortcuts import get_current_site
from directory.models import (
    Directory,
    Effector,
    Facility,
    EffectorFacility,
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

def get_addresses(request, effector):
    directory=get_directory(request)
    results, meta = db.cypher_query(
            f"""MATCH (e:Effector)-[l:LOCATION]-(f:Facility)
            WHERE l.directories=["{directory.name}"]
            AND e.uid="{effector.uid}"
            RETURN f"""
        )
    if results:
        facilities=[]
        for e in results:
            facility=Facility.inflate(e[0])
            facilities.append(facility)
        addresses = []
        for facility in facilities:
            try:
                contact = Contact.objects.get(neomodel_uid=facility.uid)
            except Contact.DoesNotExist:
                continue
            serializer = AddressSerializer(contact.address)
            addresses.append(serializer.data)
    return addresses

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

def directory_effectors(directory: Directory): 
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