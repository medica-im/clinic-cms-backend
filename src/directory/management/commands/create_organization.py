from django.utils.text import slugify
import neomodel
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from workforce.models import NetworkEdge, NodeSet, NetworkNode
from facility.models import Organization
from django.db import DatabaseError, IntegrityError
from directory.models import (
    Effector,
    HCW,
    EffectorType,
    Commune,
    Organization,
    OrganizationType,
    Facility,
)
from addressbook.models import Contact, Address
from access.models import Role

from neomodel import Q
import uuid
from addressbook.wikidata import WikiDataQueryResults
from django.core.cache import cache
from django.conf import settings
from rdflib.plugins.shared.jsonld.keys import NONE

WIKIDATA_TTL = 60 * 60

import logging

logger = logging.getLogger(__name__)


def wikidata(code: str, select: str):
    """
    Get 2-letter country code from city wikidata code.
    """
    query=f"""
        SELECT ?postalCode ?countryCode WHERE {{
        wd:{code} wdt:P17 ?country .
        ?country wdt:P297 ?countryCode .
        wd:{code} wdt:P281 ?postalCode .
        }}
        """
    data_extracter = WikiDataQueryResults(query)
    df = data_extracter.load_as_dataframe()
    cache.set(
        f"postal_code_{code}",
        df.postalCode[0],
        WIKIDATA_TTL
    )
    cache.set(
        f"country_code_{code}",
        df.countryCode[0],
        WIKIDATA_TTL
    )
    if select=="countryCode":
        return df.countryCode[0]
    elif select=="postalCode":
        return df.postalCode[0]

def get_country_code(code: str)->str:
    country_code = cache.get_or_set(
        f"country_code_{code}",
        lambda: wikidata(code, "countryCode"),
        WIKIDATA_TTL
    )
    return country_code

def get_postal_code(code: str)->str:
    postal_code = cache.get_or_set(
        f"postal_code_{code}",
        lambda: wikidata(code, "postalCode"),
        WIKIDATA_TTL
    )
    return postal_code

def is_valid_uuid(val):
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False

def display_relationship(rel):
    return [
        c.name_fr or c.label_fr or c.concept_en
        for c in rel.all()
    ]

class Command(BaseCommand):
    help = 'Create Effector node on neo4j'

    def create_node(
        self,
        label_en,
        label_fr,
        name_en,
        name_fr,
    ):
        node=None
        created=False
        try:
            node=Organization(
                label_en=label_en,
                label_fr=label_fr,
                name_en=name_en,
                name_fr=name_fr,
            ).save()
            created=True
        except Exception as e:
            #logger.error(e)
            node=Organization.nodes.filter(
                Q(label_en=label_en)
                | Q(label_fr=label_fr)
                | Q(name_en=name_en)
                | Q(name_fr=name_fr)
            )[0]
        if node and isinstance(node, Organization):
            logger.debug(f'{"new" if created else ""} node: {node=}')
        return node

    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def add_arguments(self, parser):
        parser.add_argument('--label_fr', type=str)
        parser.add_argument('--label_en', type=str)   
        parser.add_argument('--name_fr', type=str)
        parser.add_argument('--name_en', type=str)
        parser.add_argument('--type', type=str)
        parser.add_argument('--commune', type=str)
        parser.add_argument('--organization', type=str)
        parser.add_argument(
            '--f',
            action='store_true',
            help='do not create facility'
        )

    def handle(self, *args, **options):
        label_en=options['label_en']
        label_fr=options['label_fr']
        name_en=options['name_en']
        name_fr=options['name_fr']
        label_fr=label_fr or name_fr
        label_en=label_en or name_en
        organization = self.create_node(
            label_en=label_en,
            label_fr=label_fr,
            name_en=name_en,
            name_fr=name_fr
        )
        type_str=options['type']
        if is_valid_uuid(type_str):
            try:
                organization_type=OrganizationType.nodes.get(uid=type_str)
            except neomodel.DoesNotExist as e:
                self.warn(f'{e}')
                return
        else:     
            organization_type_qs = OrganizationType.nodes.filter(
                Q(label_fr=type_str)
                | Q(label_en=type_str)
                | Q(name_fr=type_str)
                | Q(name_fr=type_str)
            )
            if not organization_type_qs:
                self.warn(f"No EffectorType instance found for {type_str}")
                return
            elif len(organization_type_qs)>1:
                self.warn(f"More than one EffectorType instance found for {type_str}")
                return
            organization_type=organization_type_qs[0]
        organization.type.connect(organization_type)
        commune_str=options['commune']
        if is_valid_uuid(commune_str):
            try:
                commune=Commune.nodes.get(uid=commune_str)
            except neomodel.DoesNotExist as e:
                self.warn(f'{e}')
                return
        else:     
            commune_qs= Commune.nodes.filter(name_fr=commune_str)
            if not commune_qs:
                self.warn(f"No Commune instance found for {commune_str}")
                return
            elif len(commune_qs)>1:
                self.warn(f"More than one Commune instance found for {commune_str}")
                return
            commune=commune_qs[0]
        organization.commune.connect(commune)
        if options['organization']:
            organization_str=options['organization']
            if is_valid_uuid(organization_str):
                try:
                    o=Organization.nodes.get(uid=organization_str)
                except neomodel.DoesNotExist as e:
                    self.warn(f'{e}')
                    return
            else:     
                organization_qs= Organization.nodes.filter(
                    Q(name_fr=organization_str)
                    | Q(label_fr=organization_str)
                )
                if not organization_qs:
                    self.warn(
                        f"No Organization instance found for "
                        f"{organization_str}"
                    )
                elif len(organization_qs)>1:
                    self.warn(
                        "More than one Organization instance found for "
                        f"{organization_str}"
                    )
                    return
                o=organization_qs[0]
            organization.organization.connect(o)
        if not options['f']:
            logger.debug(f"{get_country_code(commune.wikidata)=}")
            logger.debug(f"{get_postal_code(commune.wikidata)=}")
            facility = None
            for f in Facility.nodes.all():
                logger.debug(f)
                if organization.uid in [ o.uid for o in f.organization.all()]:
                    logger.debug(f)
                    facility=f
            if not facility:
                facility=Facility().save()
            facility.organization.connect(organization)
            facility.commune.connect(commune)
            try:
                contact, _ = Contact.objects.get_or_create(
                    neomodel_uid=facility.uid
                )
            except Exception as e:
                logger.debug(e)
                return
            try:
                address, _ = Address.objects.get_or_create(
                    contact=contact,
                    city=commune.name_fr,
                    country=get_country_code(commune.wikidata),
                    zip=get_postal_code(commune.wikidata)
                )
                address.roles.set(Role.objects.all())
            except Exception as e:
                logger.debug(e)
                return
        self.warn(
            f"name_fr: {organization.name_fr}\n"
            f"label_fr: {organization.label_fr}\n"
            f"Commune: {display_relationship(organization.commune)}\n"
            f"OrganizationType: {display_relationship(organization.type)}"
        )