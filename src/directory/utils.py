import logging
from django.contrib.sites.shortcuts import get_current_site
from directory.models import Directory, Effector
from neomodel import db

logger = logging.getLogger(__name__)

def get_directory(request):
    site = get_current_site(request)
    try:
        dir = Directory.objects.get(site=site)
        return dir
    except Directory.DoesNotExist:
        return

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