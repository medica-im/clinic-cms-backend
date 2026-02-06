import logging
from time import time_ns
from neomodel import (
    config,
    AsyncStructuredNode,
    ArrayProperty,
    BooleanProperty,
    StringProperty,
    IntegerProperty,
    UniqueIdProperty,
    AsyncRelationshipTo,
    AsyncRelationshipFrom,
    AsyncRelationship,
    AsyncStructuredRel,
)
from django.utils.translation import get_language
from access.roles import ROLES

logger = logging.getLogger(__name__)


class Role(AsyncStructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True)
    label_en = StringProperty()
    label_fr = StringProperty()
    description_en = StringProperty()
    description_fr = StringProperty()


class Access(AsyncStructuredNode):
    uid = UniqueIdProperty()
    role = StringProperty(
        required=True,
        choices=ROLES,
        index=True
    )
    user = AsyncRelationshipFrom(
        'directory.models.graph.User',
        'HAS_ACCESS'
    )
    entry = AsyncRelationshipTo(
        'directory.models.graph.Entry',
        'ACCESS_TO'
    )
    createdAt = IntegerProperty(default=lambda: time_ns() // 1_000_000)
    createdBy = AsyncRelationshipTo('User', 'CREATED_BY')
    active = BooleanProperty(
        index=True,
        default=True
    )


class Invitee(AsyncStructuredNode):
    uid = UniqueIdProperty()
    email = StringProperty()
    name = StringProperty()
    createdAt = IntegerProperty(default=lambda: time_ns() // 1_000_000)
    createdBy = AsyncRelationshipTo('User', 'CREATED_BY')
    role = StringProperty(required=True, choices=ROLES)
    entry = AsyncRelationshipTo('directory.models.agraph.Entry', 'INVITED_TO')
    active = BooleanProperty(
        index=True,
        default=True)


class User(AsyncStructuredNode):
    uid = UniqueIdProperty()
    invitee = StringProperty()
    email = StringProperty()
    name = StringProperty()
    createdAt = IntegerProperty(default=lambda: time_ns() // 1_000_000)
    createdBy = AsyncRelationshipTo('User', 'CREATED_BY')
    access = AsyncRelationshipTo('Access', 'HAS_ACCESS')
    accounts = AsyncRelationshipTo('Account', 'HAS_ACCOUNT')


class Account(AsyncStructuredNode):
    uid = UniqueIdProperty()
    iss = StringProperty()
    sub = StringProperty(unique_index=True)
    user = AsyncRelationshipFrom('User', 'HAS_ACCOUNT')
    createdAt = IntegerProperty(default=lambda: time_ns() // 1_000_000)
