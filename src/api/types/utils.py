from typing import Annotated, TypeAlias
from pydantic import BeforeValidator

def _empty_str_to_none(v: str | None) -> None:
    if v is None:
        return None
    if v == '':
        return None
    raise ValueError('Value is not empty') # Not str or None, Fall to next type. e.g. a non-empty str

EmptyStrToNone: TypeAlias = Annotated[None, BeforeValidator(_empty_str_to_none)]