import io
import json
import logging
from typing import Annotated

import pandas as pd
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from neomodel import adb

from access.models import BatchInviteeJob
from access.roles import ROLES
from access.tasks import process_batch_invitees
from api.auth import JWT, authorize_api
from api.types.batch_invitee import (
    BatchInviteeCreateResponse,
    BatchInviteeJobDetail,
    BatchInviteeJobListItem,
    BatchInviteeMapping,
    BatchInviteeParseResponse,
    BatchInviteeProgress,
)
from api.utils import get_site_from_request
from facility.models import Organization

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_ROWS = 500
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".ods"}


def _get_extension(filename: str | None) -> str:
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided",
        )
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )
    return ext


def _read_file_to_dataframe(contents: bytes, ext: str) -> pd.DataFrame:
    try:
        if ext == ".csv":
            for encoding in ["utf-8", "latin-1", "cp1252"]:
                try:
                    return pd.read_csv(
                        io.BytesIO(contents),
                        encoding=encoding,
                        dtype=str,
                        keep_default_na=False,
                    )
                except UnicodeDecodeError:
                    continue
            raise ValueError("Could not decode CSV with any supported encoding")
        elif ext == ".xlsx":
            return pd.read_excel(
                io.BytesIO(contents),
                engine="openpyxl",
                dtype=str,
                keep_default_na=False,
            )
        elif ext == ".ods":
            return pd.read_excel(
                io.BytesIO(contents),
                engine="odf",
                dtype=str,
                keep_default_na=False,
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse file: {str(e)}",
        )


def _apply_mapping(df: pd.DataFrame, mapping: BatchInviteeMapping) -> list[dict]:
    rows = []
    for _, row in df.iterrows():
        email = str(row.get(mapping.email_column, "")).strip()
        if not email:
            continue

        name = ""
        if mapping.name_column and mapping.name_column in df.columns:
            name = str(row.get(mapping.name_column, "")).strip()
        elif mapping.first_name_column or mapping.last_name_column:
            parts = []
            if mapping.first_name_column and mapping.first_name_column in df.columns:
                parts.append(str(row.get(mapping.first_name_column, "")).strip())
            if mapping.last_name_column and mapping.last_name_column in df.columns:
                parts.append(str(row.get(mapping.last_name_column, "")).strip())
            name = " ".join(p for p in parts if p)

        rows.append({"email": email, "name": name})
    return rows


async def _get_organization_entry_uid(request: Request) -> tuple[str, str]:
    site = await get_site_from_request(request)
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
    return organization.neomodel_uid.hex, site.domain


@router.post("/batch-invitees/parse", response_model=BatchInviteeParseResponse)
async def parse_batch_invitees(
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
    file: UploadFile = File(...),
):
    await authorize_api("invitees_v2", request, jwt)

    ext = _get_extension(file.filename)
    contents = await file.read()
    df = _read_file_to_dataframe(contents, ext)

    if df.empty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File contains no data",
        )

    return BatchInviteeParseResponse(
        columns=df.columns.tolist(),
        preview_rows=df.head(2).to_dict(orient="records"),
    )


@router.post(
    "/batch-invitees/create",
    response_model=BatchInviteeCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_batch_invitees(
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
    file: UploadFile = File(...),
    mapping_json: str = Form(...),
    role: str = Form(...),
    send_emails: bool = Form(True),
):
    await authorize_api("invitees_v2", request, jwt)

    if role not in ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {role}. Allowed: {list(ROLES.keys())}",
        )

    entry_uid, site_domain = await _get_organization_entry_uid(request)

    if role == "superuser":
        from api.auth import get_neo4j_role, get_user, get_role
        site = await get_site_from_request(request)
        neo4j_role = await get_neo4j_role(jwt, site)
        if not neo4j_role:
            user = await get_user(jwt)
            _role = await get_role(user, site)
            neo4j_role = _role.name
        if neo4j_role != "superuser":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can create superuser invitees",
            )

    try:
        mapping_data = json.loads(mapping_json)
        mapping = BatchInviteeMapping(**mapping_data)
    except (json.JSONDecodeError, Exception) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid mapping: {str(e)}",
        )

    ext = _get_extension(file.filename)
    contents = await file.read()
    df = _read_file_to_dataframe(contents, ext)

    if df.empty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File contains no data",
        )

    if mapping.email_column not in df.columns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email column '{mapping.email_column}' not found in file",
        )

    rows = _apply_mapping(df, mapping)

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid rows found after applying column mapping",
        )

    if len(rows) > MAX_ROWS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many rows: {len(rows)}. Maximum is {MAX_ROWS}.",
        )

    user_sub = jwt.get("providerAccountId", "")
    if not user_sub:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No providerAccountId in JWT",
        )

    user_uid_query = """
    MATCH (a:Account {sub: $sub})<-[:HAS_ACCOUNT]-(u:User)
    RETURN u.uid AS uid
    """
    results, _ = await adb.cypher_query(user_uid_query, {"sub": user_sub})
    user_uid = results[0][0] if results else ""

    job = await BatchInviteeJob.objects.acreate(
        organization_neomodel_uid=entry_uid,
        user_uid=user_uid,
        total_rows=len(rows),
        role=role,
        send_emails=send_emails,
        status=BatchInviteeJob.Status.PENDING,
    )

    task = process_batch_invitees.delay(
        job_id=job.id,
        rows=rows,
        entry_uid=entry_uid,
        user_sub=user_sub,
        role=role,
        send_emails=send_emails,
        site_domain=site_domain,
    )

    job.celery_task_id = task.id
    await job.asave(update_fields=["celery_task_id"])

    return BatchInviteeCreateResponse(
        job_uid=str(job.uid),
        status=job.status,
    )


@router.get("/batch-invitees/{job_uid}/progress", response_model=BatchInviteeProgress)
async def get_batch_invitees_progress(
    job_uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    await authorize_api("invitees_v2", request, jwt)
    entry_uid, _ = await _get_organization_entry_uid(request)

    try:
        job = await BatchInviteeJob.objects.aget(
            uid=job_uid,
            organization_neomodel_uid=entry_uid,
        )
    except BatchInviteeJob.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch job not found",
        )

    percentage = (job.processed_rows / job.total_rows * 100) if job.total_rows > 0 else 0

    return BatchInviteeProgress(
        uid=str(job.uid),
        status=job.status,
        total_rows=job.total_rows,
        processed_rows=job.processed_rows,
        successful_count=job.successful_count,
        failed_count=job.failed_count,
        skipped_duplicate_email_count=job.skipped_duplicate_email_count,
        skipped_active_user_count=job.skipped_active_user_count,
        failed_email_count=job.failed_email_count,
        percentage=round(percentage, 1),
    )


@router.post("/batch-invitees/{job_uid}/cancel")
async def cancel_batch_invitees(
    job_uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    await authorize_api("invitees_v2", request, jwt)
    entry_uid, _ = await _get_organization_entry_uid(request)

    try:
        job = await BatchInviteeJob.objects.aget(
            uid=job_uid,
            organization_neomodel_uid=entry_uid,
        )
    except BatchInviteeJob.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch job not found",
        )

    if job.status not in (
        BatchInviteeJob.Status.PENDING,
        BatchInviteeJob.Status.PROCESSING,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job with status: {job.status}",
        )

    job.status = BatchInviteeJob.Status.CANCELLED
    await job.asave(update_fields=["status"])

    if job.celery_task_id:
        from backend.celery import app as celery_app
        celery_app.control.revoke(job.celery_task_id, terminate=True)

    return {"message": "Job cancellation requested", "status": "cancelled"}


@router.get("/batch-invitees", response_model=list[BatchInviteeJobListItem])
async def list_batch_invitees(
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    await authorize_api("invitees_v2", request, jwt)
    entry_uid, _ = await _get_organization_entry_uid(request)

    jobs = []
    async for job in BatchInviteeJob.objects.filter(
        organization_neomodel_uid=entry_uid
    ).values(
        "uid",
        "created_at",
        "status",
        "total_rows",
        "successful_count",
        "failed_count",
        "skipped_duplicate_email_count",
        "skipped_active_user_count",
        "failed_email_count",
        "role",
    ):
        job["uid"] = str(job["uid"])
        jobs.append(BatchInviteeJobListItem(**job))

    return jobs


@router.get("/batch-invitees/{job_uid}", response_model=BatchInviteeJobDetail)
async def get_batch_invitee_job(
    job_uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    await authorize_api("invitees_v2", request, jwt)
    entry_uid, _ = await _get_organization_entry_uid(request)

    try:
        job = await BatchInviteeJob.objects.aget(
            uid=job_uid,
            organization_neomodel_uid=entry_uid,
        )
    except BatchInviteeJob.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch job not found",
        )

    percentage = (job.processed_rows / job.total_rows * 100) if job.total_rows > 0 else 0

    return BatchInviteeJobDetail(
        uid=str(job.uid),
        status=job.status,
        total_rows=job.total_rows,
        processed_rows=job.processed_rows,
        successful_count=job.successful_count,
        failed_count=job.failed_count,
        skipped_duplicate_email_count=job.skipped_duplicate_email_count,
        skipped_active_user_count=job.skipped_active_user_count,
        failed_email_count=job.failed_email_count,
        percentage=round(percentage, 1),
        summary=job.summary,
        created_at=job.created_at,
        role=job.role,
        send_emails=job.send_emails,
    )
