import logging
import json
from neomodel import db
from directory.models import (
    Directory,
    Organization,
    OrganizationType,
    Commune,
    Website
)

logger = logging.getLogger(__name__)

def get_organizations(
        directory: Directory|None = None,
        uid: str|None = None,
        label: str = "Organization",
        active: bool = True,
    ):
    if uid:
        query=f"""MATCH (n:{label})
        WHERE n.uid="{uid}"
        RETURN n;"""
    else:
        query=f"""MATCH (n:{label})
        RETURN n;"""
    results, cols = db.cypher_query(query)
    _organizations=[]
    try:
        for row in results:
            org=Organization.inflate(row[cols.index('n')])
            org=org.__properties__
            try:
                del org['element_id_property']
            except KeyError:
                pass
            _organizations.append(org)
    except:
        pass
    logger.debug(_organizations)
    if uid:
        return _organizations[0]
    return _organizations

def create_organization(kwargs):
    node = Organization(
        name_fr=kwargs["name_fr"],
        label_fr=kwargs["label_fr"]
    ).save()
    commune=kwargs["commune"]
    if commune:
        try:
            commune_node = Commune.nodes.get(uid=commune)
            node.commune.connect(commune_node)
        except Exception as e:
            return e
    type = kwargs["type"]
    if type:
        try:
            organization_type=OrganizationType.nodes.get(uid=type)
            node.type.connect(organization_type)
        except Exception as e:
            return e
    organization = kwargs["organization"]
    if organization:
        try:
            organization_node=Organization.nodes.get(uid=organization)
            node.organization.connect(organization_node)
        except Exception as e:
            return e
    website_url=kwargs["website"]
    if website_url:
        try:
            website_node=Website.nodes.get(url=website_url)
        except Exception as e:
            website_node=Website(url=website_url).save()
        node.website.connect(website_node)
    return node

def get_organization_types(
        directory: Directory|None = None,
        uid: str|None = None,
        label: str = "OrganizationType",
        active: bool = True,
    ):
    if uid:
        query=f"""MATCH (n:{label})
        WHERE n.uid="{uid}"
        RETURN n;"""
    else:
        query=f"""MATCH (n:{label})
        RETURN n;"""
    results, cols = db.cypher_query(query)
    nodes=[]
    try:
        for row in results:
            org=OrganizationType.inflate(row[cols.index('n')])
            org=org.__properties__ 
            nodes.append(org)
    except:
        pass
    if uid:
        return nodes[0]
    return nodes