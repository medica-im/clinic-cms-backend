import logging
from time import time_ns
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
from access.roles import ROLES

logger=logging.getLogger(__name__)

class Role(StructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True)
    description_en = StringProperty()
    description_fr = StringProperty()


class User(StructuredNode):
    uid = UniqueIdProperty()
    invitee = StringProperty()
    email = StringProperty(unique_index=True)
    name = StringProperty()
    createdAt = IntegerProperty(default=lambda: time_ns() // 1_000_000)
    createdBy = RelationshipTo('User', 'CREATED_BY')
    access = RelationshipTo('Access', 'HAS_ACCESS')
    accounts = RelationshipTo('Account', 'HAS_ACCOUNT')


class Account(StructuredNode):
    uid = UniqueIdProperty()
    iss = StringProperty()
    sub = StringProperty(unique_index=True)
    user = RelationshipFrom('User', 'HAS_ACCOUNT')
    createdAt = IntegerProperty(default=lambda: time_ns() // 1_000_000)


class Access(StructuredNode):
    uid = UniqueIdProperty()
    role = StringProperty(
        required=True,
        choices=ROLES,
        index=True
    )
    user = RelationshipFrom(
        'User',
        'HAS_ACCESS'
    )
    entry = RelationshipTo(
        'directory.models.graph.Entry',
        'ACCESS_TO'
    )
    createdAt = IntegerProperty(default=lambda: time_ns() // 1_000_000)
    createdBy = RelationshipTo('User', 'CREATED_BY')
    # Kept in step with access/asyncneomodels.py, which is the copy the API
    # actually uses; see the comments there for what each of these is for. The
    # two definitions describe the same nodes, so a field added to one and not
    # the other is a field that exists or not depending on which import ran —
    # which is how label_fr survived here after being dropped everywhere else.
    createdByRole = StringProperty(choices=ROLES)
    active = BooleanProperty(
        index=True,
        default=True
    )
    supersededAt = IntegerProperty()
    supersededBy = RelationshipTo('User', 'SUPERSEDED_BY')
    suspendedAt = IntegerProperty()
    suspendedBy = RelationshipTo('User', 'SUSPENDED_BY')
    suspensionReason = StringProperty()


class Invitee(StructuredNode):
    uid = UniqueIdProperty()
    email = StringProperty()
    name = StringProperty()
    createdAt = IntegerProperty(default=lambda: time_ns() // 1_000_000)
    createdBy = RelationshipTo('User', 'CREATED_BY')
    role = StringProperty(required=True, choices=ROLES)
    entry = RelationshipTo('Entry', 'INVITED_TO')
    active = BooleanProperty(
        index=True,
        default=True)
    redeemedAt = IntegerProperty()