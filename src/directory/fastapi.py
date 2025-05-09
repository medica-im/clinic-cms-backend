import logging
import json
from typing import Union
from pydantic import ValidationError
from api.types.organization_types import OrganizationTypePy
from api.types.organization import OrganizationPy
from api.types.geography import Commune, DepartmentOfFrance
from neomodel import db
from directory.models import (
    Directory,
    Organization,
    OrganizationType,
    Commune,
    Website,
    DepartmentOfFrance
)

logger = logging.getLogger(__name__)

def get_organization(
        directory: Directory|None = None,
        uid: str|None = None,
        label: str = "Organization",
        active: bool = True,
    ) -> OrganizationPy:
    return get_organizations(
        directory=directory,
        uid=uid,
        active=active
    )[0]

def get_organizations(
        directory: Directory|None = None,
        uid: str|None = None,
        label: str = "Organization",
        active: bool = True,
    ) -> list[OrganizationPy]:
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
    orgs: list[OrganizationPy]=[]
    for row in results:
        org=Organization.inflate(row[cols.index('o')])
        org_dct=org.__properties__
        org_type=OrganizationType.inflate(row[cols.index('t')])
        org_type_dct=org_type.__properties__
        org_dct["type"]=org_type_dct
        commune=Commune.inflate(row[cols.index('c')])
        commune_dct=commune.__properties__
        dpt=DepartmentOfFrance.inflate(row[cols.index('d')])
        dpt_dct=dpt.__properties__
        commune_dct["department"]=dpt_dct
        org_dct["commune"]=commune_dct
        try:
            web=Website.inflate(row[cols.index('w')])
            web_dct=web.__properties__
            org_dct["website"]=web_dct
        except TypeError:
            pass
        try:
            org=OrganizationPy.model_validate(org_dct)
            orgs.append(org)
        except ValidationError as e:
            logger.debug(e)
            raise ValidationError(e)
    return orgs

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
    active: bool = True) -> OrganizationTypePy:
    return get_organization_types(
        directory=directory,
        uid=uid,
        active=active
    )[0]

def get_organization_types(
        directory: Directory|None = None,
        uid: str|None = None,
        active: bool = True
    )->list[OrganizationTypePy]:
    label: str = "OrganizationType"
    if uid:
        query=f"""MATCH (n:{label})
        WHERE n.uid="{uid}"
        RETURN n;"""
    else:
        query=f"""MATCH (n:{label})
        RETURN n;"""
    results, cols = db.cypher_query(query)
    nodes: list[OrganizationTypePy]=[]
    for row in results:
        org=OrganizationType.inflate(row[cols.index('n')])
        logger.debug(org.__dict__)
        logger.debug(org.__properties__)
        logger.debug(org)
        try:
            org_dct=org.__properties__
            org=OrganizationTypePy.model_validate(org_dct)
            logger.debug(org)
            nodes.append(org)
        except ValidationError as e:
            logger.debug(e)
            raise ValidationError(e)
    return nodes