import logging
from typing import Annotated
from uuid import uuid4
from fastapi import APIRouter, Request, Depends, status, HTTPException
from neomodel import adb
from api.auth import JWT, authorize_api
from api.types.organization_role import (
    OrganizationRolePost,
    OrganizationRolePatch,
    OrganizationRoleResponse,
    OrganizationRoleLabelsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/organization-roles")
async def list_organization_roles(
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
) -> list[OrganizationRoleResponse]:
    await authorize_api("organization-role", request, jwt)
    query = """
    MATCH (r:OrganizationRole)
    RETURN r
    """
    results, _ = await adb.cypher_query(query, resolve_objects=False)
    return [
        OrganizationRoleResponse(
            uid=dict(row[0])["uid"],
            label=dict(row[0]).get("label"),
        )
        for row in results
    ]


@router.post("/organization-roles", status_code=status.HTTP_201_CREATED)
async def create_organization_role(
    item: OrganizationRolePost,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
) -> OrganizationRoleResponse:
    await authorize_api("organization-role", request, jwt)
    uid = uuid4().hex
    query = """
    CREATE (r:OrganizationRole {uid: $uid, label: $label})
    RETURN r
    """
    results, _ = await adb.cypher_query(
        query, {"uid": uid, "label": item.label}, resolve_objects=False
    )
    props = dict(results[0][0])
    return OrganizationRoleResponse(uid=props["uid"], label=props.get("label"))


@router.patch("/organization-roles/{uid}")
async def update_organization_role(
    uid: str,
    item: OrganizationRolePatch,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
) -> OrganizationRoleResponse:
    await authorize_api("organization-role", request, jwt)

    fields = item.model_fields_set
    set_clauses = []
    params: dict = {"uid": uid}

    if "label" in fields:
        set_clauses.append("r.label = $label")
        params["label"] = item.label

    set_part = f"SET {', '.join(set_clauses)}" if set_clauses else ""
    query = f"""
    MATCH (r:OrganizationRole {{uid: $uid}})
    {set_part}
    RETURN r
    """
    results, _ = await adb.cypher_query(query, params, resolve_objects=False)
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OrganizationRole not found"
        )
    props = dict(results[0][0])
    return OrganizationRoleResponse(uid=props["uid"], label=props.get("label"))


@router.delete("/organization-roles/{uid}")
async def delete_organization_role(
    uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    await authorize_api("organization-role", request, jwt)

    # Check if any Officer is linked to this role
    check_query = """
    MATCH (o:Officer)-[:HAS_ROLE]->(r:OrganizationRole {uid: $uid})
    RETURN count(o) AS officer_count
    """
    results, _ = await adb.cypher_query(check_query, {"uid": uid})
    if results and results[0][0] > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete OrganizationRole: linked to one or more Officers"
        )

    delete_query = """
    MATCH (r:OrganizationRole {uid: $uid})
    DELETE r
    RETURN true
    """
    results, _ = await adb.cypher_query(delete_query, {"uid": uid})
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OrganizationRole not found"
        )
    return {"message": "OrganizationRole deleted", "uid": uid}


@router.get("/organization-role-labels")
async def get_organization_role_labels(
    request: Request,
) -> OrganizationRoleLabelsResponse:
    from api.utils import get_site_from_request
    from facility.models import Organization
    from api.serializers.effector_type_labels import get_effector_type_labels

    site = await get_site_from_request(request)
    organization = await Organization.objects.select_related('site').aget(site=site)
    # The async builder shared with /effector-type-labels, which differs only
    # in term_type. Was the sync one in directory/views.py behind
    # sync_to_async, until that view was retired with the v1 endpoint.
    labels = await get_effector_type_labels(organization.language, "officer")
    return labels.root
