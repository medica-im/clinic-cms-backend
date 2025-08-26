from enum import Enum

class Roles(str, Enum):
    ANONYMOUS = 'anonymous'
    STAFF = 'staff'
    ADMINISTRATOR = 'administrator'
    SUPERUSER = 'superuser'
