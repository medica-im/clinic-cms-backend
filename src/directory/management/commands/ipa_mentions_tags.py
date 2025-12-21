from django.utils.text import slugify
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from workforce.models import NetworkEdge, NodeSet, NetworkNode
from facility.models import Organization
from django.db import DatabaseError, IntegrityError
from directory.models.graph import (
    EffectorType,
    TagCategory,
    Tag,
)
import uuid

import logging

logger = logging.getLogger(__name__)

IPA = "infirmier en pratique avancée"
CATEGORIES = [{
    "effector_type_name_fr": "infirmier en pratique avancée",
    "name": "ipa_mentions",
    "label": "mention IPA",
    "labelShort": "mention",
    "synonyms": ["mention infirmier en pratique avancée", "mention infirmière en pratique avancée"],
    "definition": None
}]
# category 0, name 1, label 2, labelShort 3, synonyms 4, definition 5 
TAGS = [
    ["ipa_mentions", "pcs", "pathologies chroniques stabilisées; prévention et polypathologies courantes en soins primaires", "PCS", None, None],
    ["ipa_mentions", "ooh", "oncologie et hémato-oncologie", "OOH", None, None],
    ["ipa_mentions", "mrctdr", "maladie rénale chronique, dialyse et transplantation rénale","MRCTDR", None, None],
    ["ipa_mentions", "psm", "psychiatrie et santé mentale", "PSM", None, None],
    ["ipa_mentions", "urgences", "urgences", "urgences", None, None]
]

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
        cat_count=0
        tag_count=0
        for category in CATEGORIES:
            effector_type_name_fr = category["effector_type_name_fr"]
            try:
                et = EffectorType.nodes.get(name_fr=effector_type_name_fr)
            except Exception as e:
                logger.error(e)
                return
            del(category["effector_type_name_fr"])
            cat_name = category["name"]
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
                cat_count+=1
            else:
                self.notice(f"TagCategory {cat} already exists.")
            for tag in TAGS:
                logger.debug(f"{cat.name=} {tag[0]}")
                if not (tag[0] == cat.name):
                    continue
                created=False
                try:
                    tag_node = Tag.nodes.get(name=tag[1])
                except:
                    tag_node = Tag(
                        name=tag[1],
                        label=tag[2],
                        labelShort=tag[3],
                        synonyms=tag[4],
                        definition=tag[5]
                    )
                    tag_node.save()
                    created=True
                    tag_count+=1
                if not tag_node.tag_category.all():
                    tag_node.tag_category.connect(cat)
                if created:
                    self.warn(f"New Tag: {tag_node}")
                    tag_count+=1
                else:
                    self.notice(f"Tag {tag_node} already exists.")
        self.notice(f"{cat_count} new TagCategory created.")
        self.notice(f"{tag_count} new Tag created.")