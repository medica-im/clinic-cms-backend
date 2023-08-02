import logging
from django.contrib.sites.shortcuts import get_current_site
from directory.models import Directory, Effector, Facility
from addressbook.models import Contact
from neomodel import db
from addressbook.serializers import AddressSerializer

logger = logging.getLogger(__name__)

def get_directory(request):
    site = get_current_site(request)
    try:
        dir = Directory.objects.get(site=site)
        return dir
    except Directory.DoesNotExist:
        return

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