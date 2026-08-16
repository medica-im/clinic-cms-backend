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
    AsyncOne,
    AsyncOneOrMore,
)
from django.utils.translation import get_language
from access.roles import ROLES

logger = logging.getLogger(__name__)


class Role(AsyncStructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True)
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
        'access.asyncneomodels.User',
        'HAS_ACCESS'
    )
    entry = AsyncRelationshipTo(
        'directory.models.agraph.Entry',
        'ACCESS_TO'
    )
    createdAt = IntegerProperty(default=lambda: time_ns() // 1_000_000)
    createdBy = AsyncRelationshipTo('User', 'CREATED_BY')
    # The role the actor held when they made this change, recorded rather than
    # resolved on read. An administrator who is demoted next month still acted
    # as an administrator today, and a history that looked their role up at
    # display time would quietly rewrite itself.
    createdByRole = StringProperty(choices=ROLES)
    active = BooleanProperty(
        index=True,
        default=True
    )

    # --- Supersession --------------------------------------------------------
    # A role is never edited in place: changing one deactivates this node and
    # creates another, so the previous role survives with the time it ended and
    # who ended it. createdAt/createdBy only record a beginning; without these
    # the history can say when a role started but not when it stopped, which is
    # the half an audit actually gets asked about.
    supersededAt = IntegerProperty()
    supersededBy = AsyncRelationshipTo('User', 'SUPERSEDED_BY')

    # --- Suspension ----------------------------------------------------------
    # A separate axis from `active`, deliberately. `active` answers "is this the
    # current access for this user and site"; suspension answers "is that
    # current access usable right now". One flag cannot carry both: a suspended
    # account and a superseded one would be indistinguishable, so restoring a
    # suspension would mean guessing which inactive node to revive, and a
    # suspended user could be granted a fresh role that silently arrived
    # unsuspended.
    #
    # A suspended access therefore stays active: the identity and the role
    # survive so the dashboard can say why nothing works, rather than the user
    # being silently downgraded to an ordinary registered account.
    suspendedAt = IntegerProperty()
    suspendedBy = AsyncRelationshipTo('User', 'SUSPENDED_BY')
    suspensionReason = StringProperty()


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
    redeemedAt = IntegerProperty()


class User(AsyncStructuredNode):
    uid = UniqueIdProperty()
    invitee = StringProperty()
    email = StringProperty(unique_index=True)
    name = StringProperty()
    createdAt = IntegerProperty(default=lambda: time_ns() // 1_000_000)
    createdBy = AsyncRelationshipTo('User', 'CREATED_BY')
    access = AsyncRelationshipTo('Access', 'HAS_ACCESS')
    accounts = AsyncRelationshipTo('Account', 'HAS_ACCOUNT', cardinality=AsyncOneOrMore)


class Account(AsyncStructuredNode):
    uid = UniqueIdProperty()
    iss = StringProperty()
    sub = StringProperty(unique_index=True)
    user = AsyncRelationshipFrom('User', 'HAS_ACCOUNT', cardinality=AsyncOne)
    createdAt = IntegerProperty(default=lambda: time_ns() // 1_000_000)
