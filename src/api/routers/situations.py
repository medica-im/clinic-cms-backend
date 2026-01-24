from fastapi import APIRouter, Request
from api.serializers.effector_type import get_effector_types, get_effector_type
from api.types.situation import Situation
from api.utils import get_directory
from pydantic import ValidationError
from directory.utils import async_entries_of_situation
from directory.models.agraph import AsyncGraphSituation
from django.conf import settings

router = APIRouter()

@router.get("/situations")
async def situations(request: Request) -> list[Situation]:
    directory = await get_directory(request)
    nodes = await AsyncGraphSituation.nodes.all()
    data = []
    for node in nodes:
        uid = node.uid
        name = getattr(
            node,
            f'name_{settings.LANGUAGE_CODE}',
            'name_en'
        )
        entries = await async_entries_of_situation(directory, node)
        situation = {
            "uid": uid,
            "name": name,
            "entries": entries
        }
        data.append(situation)
    return data



