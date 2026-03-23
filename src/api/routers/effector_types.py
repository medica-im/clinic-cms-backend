import logging
from typing import Annotated
from fastapi import APIRouter, Depends, Request, HTTPException, status
from api.serializers.effector_type import (
    get_effector_types,
    get_effector_type,
    create_effector_type,
    update_effector_type,
    delete_effector_type,
    disconnect_effector_type_rel,
)
from api.types.effector_type import EffectorType, EffectorTypePost, EffectorTypePatch
from api.auth import JWT, authorize_api
from directory.models.agraph import EffectorType as AsyncEffectorType

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/effector-types")
async def get_effector_types_endpoint() -> list[EffectorType]:
    return get_effector_types()

@router.get("/effector-types/{uid}")
async def get_effector_type_endpoint(uid: str) -> EffectorType:
    return get_effector_type(uid=uid)

@router.post("/effector-types", status_code=status.HTTP_201_CREATED)
async def post_effector_type(
    effector_type: EffectorTypePost,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
) -> EffectorType:
    await authorize_api("effector-types", request, jwt)
    return await create_effector_type(effector_type)

@router.patch("/effector-types/{uid}")
async def patch_effector_type(
    uid: str,
    effector_type: EffectorTypePatch,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
) -> EffectorType:
    await authorize_api("effector-types", request, jwt)
    try:
        return await update_effector_type(uid, effector_type)
    except AsyncEffectorType.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EffectorType not found")

@router.delete("/effector-types/{uid}/effector-type", status_code=status.HTTP_204_NO_CONTENT)
async def delete_effector_type_rel(
    uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    await authorize_api("effector-types", request, jwt)
    try:
        await disconnect_effector_type_rel(uid)
    except AsyncEffectorType.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EffectorType not found")

@router.delete("/effector-types/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_effector_type_node(
    uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    await authorize_api("effector-types", request, jwt)
    try:
        await delete_effector_type(uid)
    except AsyncEffectorType.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EffectorType not found")