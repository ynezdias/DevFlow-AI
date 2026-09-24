from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class CodeFinding(BaseModel):
    file_path: str
    line_number: int = Field(gt=0)
    source: Literal["ruff", "bandit", "ai"]
    category: str
    severity: Literal["low", "medium", "high"]
    title: str
    description: str
    suggestion: str | None = None


class FindingResponse(CodeFinding):
    id: UUID
    review_job_id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AnalysisFile(BaseModel):
    filename: str
    content: bytes
    patch: str
