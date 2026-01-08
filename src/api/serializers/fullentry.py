import logging
from directory.utils import find_entry, async_find_entry
from api.utils import process
from directory.tasty.fulleffectors import createEffectorRessource
from api.types.fullentry import FullEntry
from fastapi import Request, HTTPException, status
from api.auth import normalize_role

logger=logging.getLogger(__name__)

def get_fullentry(uid):
    entry_node = find_entry(uid=uid)
    entry_object = createEffectorRessource(entry_node)
    entry_pydantic = FullEntry.model_validate(entry_object.__dict__)
    return entry_pydantic

async def async_get_fullentry(uid: str, req: Request, role: str, jwt)->FullEntry:
    role = normalize_role(role)
    entry_node = await async_find_entry(uid=uid)
    entry_object = createEffectorRessource(entry_node)
    entry_dct = entry_object.__dict__
    logger.debug(f"{entry_dct=}")
    attributes = ["phones, emails"]
    scrub_entry = process(entry_dct, role, attributes)
    logger.debug(f"{scrub_entry=}")
    entry_pydantic = FullEntry.model_validate(scrub_entry)
    return entry_pydantic