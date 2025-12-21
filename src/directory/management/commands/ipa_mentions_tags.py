from django.utils.text import slugify
import neomodel
import uuid
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from workforce.models import NetworkEdge, NodeSet, NetworkNode
from facility.models import Organization
from django.db import DatabaseError, IntegrityError
from directory.models.graph import (
    Entry,
    Effector,
    HCW,
    EffectorType,
    Commune,
    Organization,
    Facility,
    Directory,
    EffectorFacility,
    TagCategory,
    Tag,
)
from neomodel import Q, db
import uuid
from directory.utils import add_label
import argparse

from django.conf import settings

import logging

logger = logging.getLogger(__name__)

def removekey(d, key):
    r = dict(d)
    del r[key]
    return r

IPA = "infirmier en pratique avancée"
CATEGORIES = [{
    "effector_type_name_fr": "infirmier en pratique avancée",
    "name": "ipa_mentions",
    "label": "mention IPA",
    "labelShort": "mention",
    "synonyms": ["mention infirmier en pratique avancée", "mention infirmière en pratique avancée"],
    "definition": None
}]
# category, name, label, labelShort, synonyms, definition 
TAGS = [
    ("ipa_mentions", "pcs", "pathologies chroniques stabilisées; prévention et polypathologies courantes en soins primaires", "PCS", None, None,),
    ("ipa_mentions", "ooh", "oncologie et hémato-oncologie", "OOH", None, None,),
    ("ipa_mentions", "mrctdr", "maladie rénale chronique, dialyse et transplantation rénale","MRCTDR", None, None,),
    ("ipa_mentions", "psm", "psychiatrie et santé mentale", "PSM", None, None,),
    ("ipa_mentions", "urgences", "urgences", "urgences", None, None,),
]

def is_valid_uuid(val):
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False

class Command(BaseCommand):
    help = 'Create IPA mentions tags.'
    
    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )
    
    def error(self, message):
        self.stdout.write(
            self.style.ERROR(message)
        )
    def notice(self, message):
        self.stdout.write(
            self.style.NOTICE(message)
        )

    def handle(self, *args, **options):
        for category in CATEGORIES:
            effector_type_name_fr = category["effector_type_name_fr"]
            try:
                et = EffectorType.nodes.get(name_fr=effector_type_name_fr)
            except Exception as e:
                logger.error(e)
                return
            del(category["effector_type_name_fr"])
            cat_name = category["name"]
            count=0
            created=False
            try:
                cat = TagCategory.nodes.get(name=cat_name)
            except:
                cat = TagCategory(**category)
                cat.save()
                created=True
                cat.effector_type.connect(et)
            if created:
                self.warn(f"New TagCategory: {cat}")
                count+=1
            else:
                self.notice(f"TagCategory {cat} already exists.")
        self.notice(f"{count} new TagCategory created.")