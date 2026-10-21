from pydantic import BaseModel, Field


class InvitationSettings(BaseModel):
    resendAfterDays: int = Field(ge=1, le=365)
