"""Types for cloning an entry between deployments."""
from pydantic import BaseModel, Field


class PeerInstanceOut(BaseModel):
    name: str
    display_name: str
    origin: str


class ExportTokenRequest(BaseModel):
    target_origin: str
    entry_uids: list[str] | None = None


class ExportTokenResponse(BaseModel):
    token: str
    expires_in: int
    directory: str
    source_origin: str


class CloneMatch(BaseModel):
    kind: str                 # "exact" | "warn"
    reason: str               # rpps | ban_id | address | name | slug | name_gender
    local_uid: str
    local: dict
    incoming: dict
    differing_fields: list[str] = Field(default_factory=list)


class ObjectPlan(BaseModel):
    matches: list[CloneMatch] = Field(default_factory=list)
    default_resolution: str = "create"   # reuse | create
    auto: bool = True
    local_uid: str | None = None


class Blocker(BaseModel):
    reason: str
    detail: str
    local_slug: str | None = None


class EntryPreflight(BaseModel):
    source_uid: str
    name: str
    effector: ObjectPlan
    facility: ObjectPlan
    blockers: list[Blocker] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    auto_clonable: bool = False


class PreflightRequest(BaseModel):
    instance: str
    token: str
    entry_uids: list[str]


class Resolution(BaseModel):
    source_uid: str
    effector: str = "create"          # reuse | create
    effector_local_uid: str | None = None
    facility: str = "create"          # reuse | create
    facility_local_uid: str | None = None
    facility_slug_override: str | None = None


class ExecuteRequest(BaseModel):
    instance: str
    token: str
    resolutions: list[Resolution]


class CloneResult(BaseModel):
    source_uid: str
    status: str                       # created | failed | skipped
    entry_uid: str | None = None
    entry_slug: str | None = None
    effector_uid: str | None = None
    facility_uid: str | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class ExecuteResponse(BaseModel):
    results: list[CloneResult]
