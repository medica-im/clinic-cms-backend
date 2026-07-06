import csv
import io
import json
import logging
import re
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Request, Depends, status, HTTPException
from fastapi.responses import StreamingResponse
from neomodel import adb

from api.types.user import ListmonkExportRequest
from api.auth import JWT
from api.neo4j_auth import get_neo4j_role
from api.utils import get_site_from_request
from facility.models import Organization

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/users/export/listmonk")
async def export_listmonk_csv(
    body: ListmonkExportRequest,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
) -> StreamingResponse:
    site = await get_site_from_request(request)
    role = await get_neo4j_role(jwt, site)
    if role != "superuser":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser role required",
        )

    try:
        organization = await Organization.objects.aget(site=site)
    except Organization.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found for this site",
        )

    if not organization.neomodel_uid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization does not have a neomodel_uid",
        )

    entry_uid = str(organization.neomodel_uid.hex)

    query = """
    MATCH (u:User)-[:HAS_ACCESS]->(ac:Access {active: true})-[:ACCESS_TO]->(e:Entry {uid: $entry_uid})
    WHERE u.uid IN $user_uids
    RETURN u.uid AS uid, u.email AS email, u.name AS name
    """
    results, _ = await adb.cypher_query(
        query, {"entry_uid": entry_uid, "user_uids": body.user_uids}
    )

    text_buf = io.StringIO()
    writer = csv.writer(text_buf)
    writer.writerow(["email", "name", "attributes"])

    for uid, email, name in results:
        if not email:
            continue
        attributes = {
            "pluriproweb": {
                "user": {
                    "uid": uid,
                    "name": name,
                },
                "organization": {
                    "name": organization.name,
                    "neomodel_uid": entry_uid,
                    "formatted_name": organization.formatted_name,
                },
            }
        }
        writer.writerow([email, name or "", json.dumps(attributes, ensure_ascii=False)])

    output = io.BytesIO(text_buf.getvalue().encode('utf-8'))
    slug = re.sub(r'[^\w\-]', '_', organization.formatted_name or organization.name)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"listmonk_{slug}_{timestamp}.csv"
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )
