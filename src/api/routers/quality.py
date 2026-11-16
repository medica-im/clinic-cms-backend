"""What an entry, or a whole directory, is missing: the quality controls (directory/quality.py).

    GET /entries/{uid}/quality         the problems of one entry, for whoever may edit it: its
                                       owner or creator, administrators and superusers
    GET /directories/{name}/quality    the directory's problems by rule, for administrators and
                                       superusers, and only for a directory of the caller's site

Warnings only: nothing here refuses a save. Answered per caller and never cached, like the
permission of the widgets it sits beside.
"""
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from api.auth import JWT
from api.graph import read
from directory.quality import directory_report, entry_facts, problems

router = APIRouter(tags=["quality"])


class Problem(BaseModel):
    code: str
    severity: str


class ReportedEntry(BaseModel):
    uid: str
    slug: str | None
    name: str
    label: str | None
    type: str | None


class RuleReport(BaseModel):
    code: str
    severity: str
    entries: list[ReportedEntry]


@dataclass
class QualityCaller:
    role: str | None
    #: The caller owns or created the entry asked about (always False for a directory).
    connected: bool
    #: The caller's site.
    site: object


async def quality_caller(request: Request, jwt: dict, entry_uid: str | None = None) -> QualityCaller:
    from api.neo4j_auth import get_neo4j_role, get_neo4j_user
    from api.utils import get_site_from_request

    site = await get_site_from_request(request)
    role = await get_neo4j_role(jwt, site) if jwt else None
    connected = False
    if entry_uid and jwt:
        user = await get_neo4j_user(jwt)
        connected = bool(user) and bool(
            await read(
                "MATCH (:Entry {uid: $e})-[r:OWNED_BY|CREATED_BY]->(u:User {uid: $u}) RETURN u.uid AS uid",
                e=entry_uid,
                u=user.uid,
            )
        )
    return QualityCaller(role=role, connected=connected, site=site)


async def directory_is_of_site(name: str, site) -> bool:
    from directory.models import Directory

    return await Directory.objects.filter(name=name, site=site).aexists()


@router.get("/entries/{uid}/quality", response_model=list[Problem])
async def get_entry_quality(uid: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    caller = await quality_caller(request, jwt, uid)
    if not (caller.role in ("administrator", "superuser") or caller.connected):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "not_allowed"})
    facts = await entry_facts(uid)
    if facts is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Entry not found")
    return [Problem(code=code, severity=severity) for code, severity in problems(facts)]


@router.get("/directories/{name}/quality", response_model=list[RuleReport])
async def get_directory_quality(name: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    caller = await quality_caller(request, jwt)
    if caller.role not in ("administrator", "superuser") or not await directory_is_of_site(name, caller.site):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "not_allowed"})
    return await directory_report(name)
