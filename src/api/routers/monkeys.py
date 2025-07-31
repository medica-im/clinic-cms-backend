import logging
from fastapi import APIRouter, status, Request
from api.types.monkey import Monkey, MonkeyPost
from directory.models.agraph import Monkey as AsyncMonkey

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/monkeys")
async def entries() -> list[Monkey]:
    monkeys = await AsyncMonkey.nodes
    return [Monkey.model_validate(monkey.__properties__) for monkey in monkeys]

@router.post("/monkeys/", status_code=status.HTTP_201_CREATED)
async def post_entry(monkey: MonkeyPost, request: Request) -> Monkey:
    _monkey = await AsyncMonkey(name=monkey.name).save()
    return Monkey.model_validate(_monkey.__properties__)
