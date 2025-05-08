import logging
import json
from typing import Union
from pydantic import ValidationError
from api.types.organization_types import OrganizationTypePy, OrganizationTypePyNeo, organization_type_exclude_keys
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
        query=f"""MATCH (o:{label})-[:IS_A]->(t:OrganizationType),
        (o)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(d:DepartmentOfFrance)
        OPTIONAL MATCH (o)-[:OFFICIAL_WEBSITE]->(w:Website)
        WHERE o.uid="{uid}"
        RETURN o,t,c,d,w;"""
    else:
        query=f"""MATCH (o:{label})-[:IS_A]->(t:OrganizationType),
        (o)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(d:DepartmentOfFrance)
        OPTIONAL MATCH (o)-[:OFFICIAL_WEBSITE]->(w:Website)
        RETURN o,t,c,d,w;"""
    results, cols = db.cypher_query(query)
    _organizations=[]
    try:
        for row in results:
            org=Organization.inflate(row[cols.index('o')])
            org=org.__properties__
            for key in ['element_id_property', 'name_en', 'label_en']:
                try:
                    del org[key]
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

def get_organization_type(
    directory: Directory|None = None,
    uid: str|None = None,
    active: bool = True) -> OrganizationTypePyNeo:
    return get_organization_types(
        directory=directory,
        uid=uid,
        active=active
    )[0]

def get_organization_types(
        directory: Directory|None = None,
        uid: str|None = None,
        active: bool = True
    )->list[OrganizationTypePyNeo]:
    label: str = "OrganizationType"
    if uid:
        query=f"""MATCH (n:{label})
        WHERE n.uid="{uid}"
        RETURN n;"""
    else:
        query=f"""MATCH (n:{label})
        RETURN n;"""
    results, cols = db.cypher_query(query)
    nodes: list[OrganizationTypePyNeo]=[]
    for row in results:
        org=OrganizationType.inflate(row[cols.index('n')])
        logger.debug(org.__dict__)
        logger.debug(org.__properties__)
        logger.debug(org)
        try:
            org_json=org.__properties__
            org=OrganizationTypePyNeo.model_validate(org_json)
            nodes.append(org)
        except ValidationError as e:
            logger.debug(e)
            raise ValidationError(e)
    return nodes