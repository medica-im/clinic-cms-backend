from enum import Enum
from pydantic import BaseModel

class Roles(str, Enum):
    """The five roles, as they travel: a name and nothing else.

    A `str` subclass so a payload carries `"staff"` rather than an object, and
    a client can compare it without unwrapping anything.

    `registered` was missing here until 2026-08-15 while existing in the
    database, so any payload carrying that role could not be represented at
    all.
    """
    ANONYMOUS = 'anonymous'
    REGISTERED = 'registered'
    STAFF = 'staff'
    ADMINISTRATOR = 'administrator'
    SUPERUSER = 'superuser'