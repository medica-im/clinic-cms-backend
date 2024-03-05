import logging
from uuid import uuid4
from neomodel import (
    config,
    StructuredNode,
    ArrayProperty,
    BooleanProperty,
    StringProperty,
    IntegerProperty,
    UniqueIdProperty,
    ArrayProperty,
    RelationshipTo,
    RelationshipFrom,
    Relationship,
    StructuredRel,
)
from django.utils.translation import get_language

logger=logging.getLogger(__name__)

class Role(StructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True)
    label_en = StringProperty(unique_index=True)
    label_fr = StringProperty(unique_index=True)
    description_en = StringProperty()
    description_fr = StringProperty()


class Access(StructuredNode):
    uid = UniqueIdProperty()
    roles = RelationshipTo(
        'Role',
        'HAS_ROLE'
    )
    effector = RelationshipTo(
        'directory.models.graph.Effector',
        'ACCESS_BY'
    )
    organization = RelationshipTo(
        'directory.models.graph.Organization',
        'ACCESS_TO'
    )