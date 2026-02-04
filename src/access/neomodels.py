import logging
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
    DateTimeProperty,
)
from django.utils.translation import get_language

logger=logging.getLogger(__name__)

ROLES = {
        'superuser': 'Superuser',
        'administrator': 'Management',
        'staff': 'Staff',
        'registered': 'Registered user',
        'anonymous': 'Anonymous visitor',
    }

class Role(StructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True)
    label_en = StringProperty()
    label_fr = StringProperty()
    description_en = StringProperty()
    description_fr = StringProperty()


class Access(StructuredNode):
    uid = UniqueIdProperty()
    role = StringProperty(
        required=True,
        choices=ROLES,
        index=True
    )
    user = RelationshipFrom(
        'directory.models.graph.User',
        'HAS_ACCESS'
    )
    entry = RelationshipTo(
        'directory.models.graph.Entry',
        'ACCESS_TO'
    )
    createdAt = DateTimeProperty(default_now=True)
    createdBy = RelationshipTo('User', 'CREATED_BY')
    active = BooleanProperty(
        index=True,
        default=True
    )


class Invitee(StructuredNode):
    uid = UniqueIdProperty()
    email = StringProperty()
    name = StringProperty()
    createdAt = DateTimeProperty(default_now=True)
    createdBy = RelationshipTo('User', 'CREATED_BY')
    role = StringProperty(required=True, choices=ROLES)
    entry = RelationshipTo('Entry', 'INVITED_TO')
    active = BooleanProperty(
        index=True,
        default=True)


class User(StructuredNode):
    uid = UniqueIdProperty()
    invitee = StringProperty()
    email = StringProperty()
    name = StringProperty()
    createdAt = DateTimeProperty(default_now=True)
    createdBy = RelationshipTo('User', 'CREATED_BY')
    access = RelationshipTo('Access', 'HAS_ACCESS')
    accounts = RelationshipTo('Account', 'HAS_ACCOUNT')


class Account(StructuredNode):
    uid = UniqueIdProperty()
    iss = StringProperty()
    sub = StringProperty(unique_index=True)
    user = RelationshipFrom('User', 'HAS_ACCOUNT')
    createdAt = DateTimeProperty(default_now=True)