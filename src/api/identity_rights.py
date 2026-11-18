"""Who may say who an entry or a place legally is.

"This entry is run by MGEN", an entry's SIREN, a facility's SIRET are claims about
legal identity that other pages repeat, so they are an administrator's or a
superuser's to make, as the directories of an entry are.
"""
import logging

from fastapi import HTTPException

logger = logging.getLogger(__name__)

IDENTITY_ROLES = ("administrator", "superuser")


def check_identity_role(role: str | None, what: str) -> None:
    if role not in IDENTITY_ROLES:
        logger.error(f"Role {role} attempted to set {what}")
        raise HTTPException(status_code=403, detail=f"Only administrators and superusers can set {what}")
