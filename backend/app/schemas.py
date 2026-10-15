"""Request and response models of the API."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# {"N1": {"Gasabo": [2027, 2028, 2029, 2030], ...}} — new students of an entry grade per district and year
Intake = dict[str, dict[str, list[int]]]


class ProjectionRequest(BaseModel):
    intake: Intake | None = Field(None, description="Intake plan; missing districts / grades take the default plan")


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=128, description="MINEDUC GIS portal username")
    password: str = Field(min_length=1, max_length=1024, description="the portal password (checked by the portal)")
    remember: bool = Field(False, description="Stay signed in on this browser (remember_days) instead of one session")


Role = Literal["admin", "viewer"]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str | None
    full_name: str | None
    role: str


class AdminUserOut(UserOut):
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class UserPatchIn(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


class ImportOut(BaseModel):
    id: int
    kind: str
    label: str
    academic_year: int | None
    file_name: str | None
    file_size: int | None
    status: str
    progress: int
    is_live: bool
    uploaded_by: str | None
    uploaded_at: datetime
    published_by: str | None
    published_at: datetime | None
    error: str | None


class ImportDetailOut(ImportOut):
    report: dict | None
    can_publish: bool
    consequence: str | None


class AuditOut(BaseModel):
    id: int
    at: datetime
    user_id: int | None
    user_username: str | None
    user_name: str | None
    action: str
    target: str
    detail: dict | None


class ScenarioIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(None, max_length=2000)
    intake: Intake


class ScenarioSummary(BaseModel):
    id: int
    name: str
    description: str | None
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    base_year: int = Field(description="the base year the plan was made for (its years are the four after it)")
    archived: bool = Field(description="made for an older base year: readable, copy it to the current years to use it")


class ScenarioCopyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ScenarioOut(ScenarioSummary):
    intake: Intake
