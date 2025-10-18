from directory.utils import find_entry, async_find_entry
from directory.tasty.fulleffectors import createEffectorRessource
from api.types.fullentry import FullEntry

def get_fullentry(uid):
    entry_node = find_entry(uid=uid)
    entry_object = createEffectorRessource(entry_node)
    entry_pydantic = FullEntry.model_validate(entry_object.__dict__)
    return entry_pydantic

async def async_get_fullentry(uid):
    entry_node = await async_find_entry(uid=uid)
    entry_object = createEffectorRessource(entry_node)
    entry_pydantic = FullEntry.model_validate(entry_object.__dict__)
    return entry_pydantic