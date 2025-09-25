from directory.utils import find_entry
from directory.tasty.fulleffectors import createEffectorRessource
from api.types.fullentry import FullEntry

async def get_fullentry(uid):
    entry_node = find_entry(uid=uid)
    entry_object = createEffectorRessource(entry_node)
    entry_pydantic = FullEntry.model_validate(entry_object)
    return entry_pydantic