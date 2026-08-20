import re
import argparse
from django.utils.text import slugify
import neomodel
from neomodel.contrib.spatial_properties import NeomodelPoint
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
from addressbook.models import Contact
from access.models import Role
from neomodel import Q
import uuid
from addressbook.wikidata import WikiDataQueryResults
from django.core.cache import cache
from django.conf import settings

import logging

logger = logging.getLogger(__name__)

def extract_dms(_str):
    deg, minutes, seconds, direction =  re.split('[°\'"]', _str)
    return (float(deg) + float(minutes)/60 + float(seconds)/(60*60)) * (-1 if direction in ['W', 'S'] else 1)

def maps_dms_to_dd(_str):
    if not _str:
        raise(ValueError("Maps string is empty!"))
    lat_dms, long_dms = _str.split('_')
    lat = extract_dms(lat_dms)
    long = extract_dms(long_dms)
    return long, lat

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

def restricted_float(x):
    try:
        x = float(x)
    except ValueError:
        raise argparse.ArgumentTypeError("%r not a floating-point literal" % (x,))

class Command(BaseCommand):
    help = 'Create Facility node on neo4j'

    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def add_arguments(self, parser):
        parser.add_argument('--commune', type=str)
        parser.add_argument('--building', type=str)
        parser.add_argument('--street', type=str)
        parser.add_argument('--geographical_complement', type=str)
        parser.add_argument('--zip', type=str)
        parser.add_argument('--name', type=str)
        parser.add_argument('--label', type=str)
        parser.add_argument('--slug', type=str)
        parser.add_argument('--tooltip_text', type=str)
        parser.add_argument('--latitude', type=str)
        parser.add_argument('--longitude', type=str)
        parser.add_argument(
            '--maps',
            type=str,
            help="""Join the two components with an underscore: 40°08'20.9"N_26°24'29.7"E"""
        )
        parser.add_argument('--zoom', type=int)

    def handle(self, *args, **options):
        commune_str=options['commune']
        if commune_str:
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

        facility=Facility().save()
        if facility:
            if commune_str and commune:
                facility.commune.connect(commune)
            if options["name"]:
                facility.name=options["name"]
            if options["label"]:
                facility.label=options["label"]
            else:
                facility.label=options["name"]
            if options["slug"]:
                slug = options["slug"]
            elif options["name"]:
                slug = slugify(options["name"])
            else:
                slug = None
            if slug:
                facility.slug=slug
            street = options["street"]
            if street:
                facility.street=street
            geo = options["geographical_complement"]
            if geo:
                facility.geographical_complement=geo
            building = options["building"]
            if building:
                facility.building=building
            zip=options["zip"]
            if zip:
                facility.zip=zip
            tt=options["tooltip_text"]
            if tt:
                facility.tooltip_text=tt
            zoom=options["zoom"]
            if zoom:
                facility.zoom=zoom
            latitude = options["latitude"]
            longitude = options["longitude"]
            maps = options["maps"]
            if latitude and longitude and maps:
                raise ValueError("Can't have maps and lat/long options")
            lng_lat=None
            if latitude and longitude:
                lng_lat = (float(longitude),float(latitude))
            elif maps:
                lng_lat = maps_dms_to_dd(maps)
            if lng_lat:
                location=NeomodelPoint(lng_lat, crs='wgs-84')
                facility.location=location
            facility.save()
        self.warn(
            f"{facility}\n"
            f"Commune: {display_relationship(facility.commune)}\n"
            f"uid: {facility.uid}\n"
            f"name: {facility.name}\n"
            f"label: {facility.label}\n"
            f"slug: {facility.slug}\n"
            f"building: {facility.building}\n"
            f"street: {facility.street}\n"
            f"geo: {facility.geographical_complement}\n"
            f"zip: {facility.zip}\n"
            f"location: {facility.location}\n"
            f"zoom: {facility.zoom}\n"
            f"tooltip_text: {facility.tooltip_text}\n"
        )