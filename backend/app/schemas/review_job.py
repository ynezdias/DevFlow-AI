from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from app.schemas.changed_file import ChangedFile, ScopeSummary


class ReviewJobCreate(BaseModel):
    repository_name: str = Field(min_length=1, max_length=255)
    pull_request_number: int = Field(gt=0)
    head_sha: str = Field(min_length=7, max_length=40)


class ReviewJobResponse(BaseModel):
    id: UUID
    repository_name: str
    pull_request_number: int
    head_sha: str
    status: Literal["queued", "processing", "completed", "failed", "superseded"]
    attempt_count: int
    installation_id: int | None = None
    github_repository_id: int | None = None
    base_sha: str | None = None
    scope_summary: ScopeSummary | None = None
    changed_files: list[ChangedFile] | None = None
    error_code: str | None = None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
