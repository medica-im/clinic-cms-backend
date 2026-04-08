import logging
from common.utils import timestamp
from uuid import uuid4
from neomodel.contrib import spatial_properties as neomodel_spatial
from neomodel import (
    AsyncStructuredNode,
    BooleanProperty,
    StringProperty,
    IntegerProperty,
    DateTimeFormatProperty,
    UniqueIdProperty,
    ArrayProperty,
    AsyncRelationshipTo,
    AsyncRelationshipFrom,
    AsyncRelationship,
    AsyncStructuredRel,
    AsyncZeroOrMore,
    AsyncZeroOrOne,
    OneOrMore,
    AsyncOne,
    EmailProperty,
    DateProperty,
)
from django.utils.translation import get_language

logger=logging.getLogger(__name__)

class OrganizationRole(AsyncStructuredNode):
    uid = UniqueIdProperty()
    label = StringProperty()


class MembershipCategory(AsyncStructuredNode):
    uid = UniqueIdProperty()
    label = StringProperty()
    entry = AsyncRelationshipTo(
        'Entry',
        'CATEGORY_OF',
        cardinality=AsyncOne
    )


class HasRoleRel(AsyncStructuredRel):
    label = StringProperty()


class Officer(AsyncStructuredNode):
    uid = UniqueIdProperty()
    start = DateProperty()
    stop = DateProperty()
    entry = AsyncRelationshipTo(
        'Entry',
        'MEMBER_OF',
        cardinality=AsyncOne
    )
    role = AsyncRelationshipTo(
        'OrganizationRole',
        'HAS_ROLE',
        model=HasRoleRel,
        cardinality=AsyncOne
    )
    effector = AsyncRelationshipTo(
        'Effector',
        'HAS_EFFECTOR',
        cardinality=AsyncOne
    )


class BoardMember(AsyncStructuredNode):
    uid = UniqueIdProperty()
    start = DateProperty()
    stop = DateProperty()
    entry = AsyncRelationshipTo(
        'Entry',
        'MEMBER_OF',
        cardinality=AsyncOne
    )
    effector = AsyncRelationshipTo(
        'Effector',
        'HAS_EFFECTOR',
        cardinality=AsyncOne
    )
    category = AsyncRelationshipTo(
        'MembershipCategory',
        'HAS_MEMBERSHIP_CATEGORY',
        cardinality=AsyncZeroOrOne
    )