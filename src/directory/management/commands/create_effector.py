from django.utils.text import slugify
import neomodel
from neomodel import db
import uuid
import argparse
from langcodes import *
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
    Facility,
    Directory,
    EffectorFacility,
    Convention,
    HealthWorker
)
from addressbook.models import Contact, PhoneNumber
from neomodel import Q, db
import uuid
from directory.utils import add_label
from neomodel.exceptions import MultipleNodesReturned

from django.conf import settings

import logging
from directory.management.commands.care_home import is_valid_uuid

logger = logging.getLogger(__name__)

def convention():
    query=""" MATCH (n:Convention) RETURN n"""
    results, meta = db.cypher_query(query, resolve_objects=True)
    names = []
    for row in results:
        names.append(row[0].name)
    return names

def third_party_payers():
    query=""" MATCH (n:ThirdPartyPayer) RETURN n"""
    results, meta = db.cypher_query(query, resolve_objects=True)
    names = []
    for row in results:
        names.append(row[0].name)
    return names

def payment_methods():
    query=""" MATCH (n:PaymentMethod) RETURN n"""
    results, meta = db.cypher_query(query, resolve_objects=True)
    pms = []
    for row in results:
        pms.append(row[0].name)
    return pms

def get_organization(organization):
    if is_valid_uuid(organization):
        try:
            return Organization.nodes.get(uid=organization)
        except neomodel.DoesNotExist as e:
            self.warn(f'{e}')
            return
    else:
        organization_qs= Organization.nodes.filter(
            Q(name_fr=organization)
            | Q(label_fr=organization)
        )
        if not organization_qs:
            self.warn(f"No Organization instance found for {organization}")
            return
        elif len(organization_qs)>1:
            self.warn(
                "More than one Organization instance found for "
                f"{organization}"
            )
            return
        return organization_qs[0]

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
        slug_fr,
        slug_en
    ):
        node=None
        created=False
        try:
            node=Effector(
                label_en=label_en,
                label_fr=label_fr,
                name_en=name_en,
                name_fr=name_fr,
                slug_fr=slug_fr,
                slug_en=slug_en
            ).save()
            created=True
        except Exception as e:
            #logger.error(e)
            node=Effector.nodes.filter(
                Q(label_en=label_en)
                | Q(label_fr=label_fr)
                | Q(name_en=name_en)
                | Q(name_fr=name_fr)
            )[0]
        if node and isinstance(node, Effector):
            logger.debug(f'{"new" if created else ""} node: {node=}')
        return node

    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def add_arguments(self, parser):
        parser.add_argument('effector', type=str)
        parser.add_argument('--label_fr', type=str)
        parser.add_argument('--label_en', type=str)   
        parser.add_argument('--name_fr', type=str)
        parser.add_argument('--name_en', type=str)
        parser.add_argument('--type', type=str)
        parser.add_argument('--commune', type=str)
        parser.add_argument('--organization', type=str)
        parser.add_argument('--division_of', type=str)
        parser.add_argument('--facility', type=str)
        parser.add_argument('--directory', type=str)
        parser.add_argument('--slug_fr', type=str)
        parser.add_argument('--slug_en', type=str)
        parser.add_argument('--carehome', action=argparse.BooleanOptionalAction)
        parser.add_argument('--carte_vitale', type=str)
        parser.add_argument(
            '--convention',
            type=str,
            help=f"Convention among {convention()}"
        )
        parser.add_argument('--rpps', type=str)
        parser.add_argument('--adeli', type=str)
        parser.add_argument(
            '--spoken_languages',
            nargs='+',
            type=str,
            help="List of ISO 639 language codes"
        )
        parser.add_argument(
            '--payment_methods',
            nargs='+',
            type=str,
            help=f"List of payment methods among {payment_methods()}"
        )
        parser.add_argument('-hw', action='store_true')
        parser.add_argument(
            '--third_party_payers',
            nargs='+',
            type=str,
            help=f"List of third party payers among {third_party_payers()}"
        )

    def handle(self, *args, **options):
        label_en=options['label_en']
        label_fr=options['label_fr']
        name_en=options['name_en']
        name_fr=options['name_fr']
        label_fr=label_fr or name_fr
        label_en=label_en or name_en
        if options['name_fr']:
            slug_fr=options['slug_fr'] or slugify(name_fr)
        else:
            slug_fr=None
        if options['name_en']:
            slug_en=options['slug_en'] or slugify(name_en)
        else:
            slug_en=None
        # effector
        effector_uid = options["effector"]
        if effector_uid and is_valid_uuid(effector_uid):
            effector = Effector.nodes.get_or_none(uid=effector_uid)
        else:
            try:
                effector = Effector.nodes.get_or_none(name_fr=name_fr)
            except MultipleNodesReturned:
                self.warn(
                    f"More than one effector found with name_fr={name_fr}")
                return
        if not effector:
            effector = self.create_node(
                label_en=label_en,
                label_fr=label_fr,
                name_en=name_en,
                name_fr=name_fr,
                slug_fr=slug_fr,
                slug_en=slug_en
            )
        if options['type']:
            type_str=options['type']
            if is_valid_uuid(type_str):
                try:
                    effector_type=EffectorType.nodes.get(uid=type_str)
                except neomodel.DoesNotExist as e:
                    self.warn(f'{e}')
                    return
            else:     
                effector_type_qs= EffectorType.nodes.filter(
                    Q(label_fr=type_str)
                    | Q(label_en=type_str)
                    | Q(name_fr=type_str)
                    | Q(name_fr=type_str)
                )
                if not effector_type_qs:
                    self.warn(f"No EffectorType instance found for {type_str}")
                    return
                elif len(effector_type_qs)>1:
                    self.warn(f"More than one EffectorType instance found for {type_str}")
                    return
                effector_type=effector_type_qs[0]
            if not effector.type:
                effector.type.connect(effector_type)
        if options['commune']:
            commune=options['commune']
            if is_valid_uuid(commune):
                try:
                    c=Commune.nodes.get(uid=commune)
                except neomodel.DoesNotExist as e:
                    self.warn(f'{e}')
                    return
            else:     
                commune_qs= Commune.nodes.filter(
                    Q(name_fr=commune)
                    | Q(name_fr=commune)
                )
                if not commune_qs:
                    self.warn(f"No Commune instance found for {commune}")
                    return
                elif len(commune_qs)>1:
                    self.warn(f"More than one Commune instance found for {commune}")
                    return
                c=commune_qs[0]
            effector.commune.connect(c)
        if options['organization']:
            organization_str=options['organization']
            o = get_organization(organization_str)
            if not o:
                return
            effector.organization.connect(o)
        if options['facility'] and options['directory']:
            directory=options['directory']
            try:
                Directory.objects.get(name=directory)
            except Directory.DoesNotExist:
                self.warn(f"Directory {directory} does not exist.")
                return
            facility_uid=options['facility']
            if facility_uid and is_valid_uuid(facility_uid):
                try:
                    f=Facility.nodes.get(uid=facility_uid)
                except neomodel.DoesNotExist as e:
                    self.warn(f'{e}')
                    return
                if facility_uid in [f.uid for f in effector.facility.all()]:
                    self.warn(f'{effector.name_fr} is already linked to facility {f}')
                else:
                    directories=[directory]
                    if (effector.facility.connect(
                        f, {"directories": directories, "uid": uuid.uuid4()})):
                        self.warn(f'{effector.name_fr} was linked to facility {f}')
        facility_uid = options['facility']
        if facility_uid and is_valid_uuid(facility_uid):
            try:
                f=Facility.nodes.get(uid=facility_uid)
            except neomodel.DoesNotExist as e:
                self.warn(f'{e}')
                return
            results, cols = db.cypher_query(
                f"""MATCH (effector)-[rel:LOCATION]-(facility)
                WHERE effector.uid="{effector.uid}" AND facility.uid="{f.uid}"
                RETURN rel"""
            )
            self.warn(f"{results}")
            rel = EffectorFacility.inflate(results[0][cols.index('rel')])
            self.warn(f"{rel.uid=}")
            contact, _created = Contact.objects.get_or_create(
                neomodel_uid=rel.uid
            )
            f"Contact:  {contact}"
        if options["carehome"]:
            add_label(effector.uid, "CareHome")
        # Carte Vitale
        cv=options["carte_vitale"]
        rel=None
        if cv and is_valid_uuid(facility_uid):
            if cv in ["yes", "oui", "true"]:
                cv=True
            elif cv in ["no", "non", "false"]:
                cv=False 
            else:
                self.warn(f"Invalid option {cv=}")
                return
            try:
                f=Facility.nodes.get(uid=facility_uid)
            except neomodel.DoesNotExist as e:
                self.warn(f'{e}')
                return
            if f in effector.facility.all():
                try:
                    rel = effector.facility.relationship(f)
                except Exception as e:
                    self.warn(
                        f"Could not find a relationship between {effector} "
                        f"and {f}: {e}"
                    )
                    return
                rel.carteVitale=cv
                rel.save()
        # division_of
        division_of = options["division_of"]
        if division_of:
            o = get_organization(division_of)
            if not o:
                return
            o.division.connect(effector)
        # convention
        convention_name=options["convention"]
        if convention_name:
            try:
                convention=Convention.nodes.get(name=convention_name)
            except neomodel.exceptions.DoesNotExist as e:
                self.warn(f'Convention name="{convention_name}" does not exist')
                return
            try:
                effector.convention.connect(convention)
            except Exception as e:
                self.warn(e)
        #add HealthcareWorker label to node
        if options["hw"]:
            query=f""" MATCH (n:Effector {{uid: "{effector.uid}"}})
            SET n :HealthWorker
            RETURN n
            """
            results, meta = db.cypher_query(query, resolve_objects=True)
            self.warn(results)
        #spoken_languages
        spoken_languages=options["spoken_languages"]
        if spoken_languages:
            try:
                hw=HealthWorker.nodes.get(uid=effector.uid)
            except Exception as e:
                self.warn(f"Is {effector} a HealthWorker?\n{e}")
                return
            ok_tags = []
            for tag in spoken_languages:
                try:
                    ok_tags.append(standardize_tag(tag))
                except LanguageTagError as e:
                    self.warn(e)
            if ok_tags:
                hw.spoken_languages = ok_tags
                hw.save()
                language_names = [
                    Language.get(tag).display_name('fr')
                    for tag in hw.spoken_languages
                ]
                self.warn(f'Spoken languages: {", ".join(language_names)}\n')
        #rpps
        rpps=options["rpps"]
        if rpps:
            try:
                hw=HealthWorker.nodes.get(uid=effector.uid)
            except Exception as e:
                self.warn(f"Is {effector} a HealthWorker?\n{e}")
                return
            hw.rpps=rpps
            hw.save()
            self.warn(f'RPPS number: "{hw.rpps}"\n')
        #ADELI
        adeli=options["adeli"]
        if adeli:
            try:
                hw=HealthWorker.nodes.get(uid=effector.uid)
            except Exception as e:
                self.warn(f"Is {effector} a HealthWorker?\n{e}")
                return
            hw.adeli=adeli
            hw.save()
            self.warn(f'ADELI number: "{hw.adeli}"\n')
        #payment_methods
        pms=options["payment_methods"]
        rel=None
        if pms and is_valid_uuid(facility_uid):
            available_pms = payment_methods()
            for pm in pms:
                if pm not in available_pms:
                    self.warn(
                        f'Invalid option: "{pm=}"\n'
                        f'Valid options: {available_pms}'
                    )
                    return
            try:
                f=Facility.nodes.get(uid=facility_uid)
            except neomodel.DoesNotExist as e:
                self.warn(f'{e}')
                return
            if f in effector.facility.all():
                try:
                    rel = effector.facility.relationship(f)
                except Exception as e:
                    self.warn(
                        f"Could not find a relationship between {effector} "
                        f"and {f}: {e}"
                    )
                    return
                rel.payment=pms
                rel.save()
        # third party payers
        tpps=options["third_party_payers"]
        rel=None
        if tpps and is_valid_uuid(facility_uid):
            available_tpps = third_party_payers()
            for tpp in tpps:
                if tpp not in available_tpps:
                    self.warn(
                        f'Invalid option: "{tpp=}"\n'
                        f'Valid options: {available_tpps}'
                    )
                    return
            try:
                f=Facility.nodes.get(uid=facility_uid)
            except neomodel.DoesNotExist as e:
                self.warn(f'{e}')
                return
            if f in effector.facility.all():
                try:
                    rel = effector.facility.relationship(f)
                except Exception as e:
                    self.warn(
                        f"Could not find a relationship between {effector} "
                        f"and {f}: {e}"
                    )
                    return
                rel.thirdPartyPayment=tpps
                rel.save()

        warning = (
            f"uid: {effector.uid}\n"
            f"name_fr: {effector.name_fr}\n"
            f"label_fr: {effector.label_fr}\n"
            f"EffectorType: {display_relationship(effector.type)}\n"
            f"Effector facility: {effector.facility.all()}\n"
        )
        try:
            hw=HealthWorker.nodes.get(uid=effector.uid)
        except Exception as e:
            warning+=f"This effector is not a HealthWorker ({e})\n"
            hw=None
        if hw:
            warning+=f"RPPS: {hw.rpps}\n"
            warning+=f"ADELI: {hw.adeli}\n"
            warning+=f"Spoken languages: {hw.spoken_languages}\n"
            convention = (
                effector.convention.all()[0].name
                if effector.convention.all()
                else None
            )
            warning+=(f"Convention: {convention} \n")
        if hw and effector and options["facility"] and f:
            rel = effector.facility.relationship(f)
            if rel:
                warning+=f"Carte Vitale: {rel.carteVitale}\n"
                warning+=f"Payment methods: {rel.payment}\n"
                warning+=f"Third party payers: {rel.thirdPartyPayment}\n"
        self.warn(warning)