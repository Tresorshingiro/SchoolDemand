"""Request and response models of the API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# {"N1": {"Gasabo": [2027, 2028, 2029, 2030], ...}} — new students of an entry grade per district and year
Intake = dict[str, dict[str, list[int]]]


class ProjectionRequest(BaseModel):
    intake: Intake | None = Field(None, description="Intake plan; missing districts / grades take the default plan")


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)
    remember: bool = Field(False, description="Stay signed in on this browser (remember_days) instead of one session")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str | None


class ScenarioIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(None, max_length=2000)
    intake: Intake


class ScenarioSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None
    created_by: str | None
    created_at: datetime
    updated_at: datetime


class ScenarioOut(ScenarioSummary):
    intake: Intake
