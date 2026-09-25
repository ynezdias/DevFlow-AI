from pydantic import BaseModel, Field


class ChangedFile(BaseModel):
    filename: str = Field(min_length=1)
    status: str
    additions: int = Field(ge=0)
    deletions: int = Field(ge=0)
    changes: int = Field(ge=0)
    patch: str | None = None


class PullRequestSnapshot(BaseModel):
    github_repository_id: int
    base_sha: str
    head_sha: str
    files: list[ChangedFile]


class SkippedFile(BaseModel):
    filename: str
    reason: str
    patch_chars: int


class ScopeSummary(BaseModel):
    ai: dict | None = None
    report: dict | None = None
    limited: bool
    total_files: int
    selected_files: int
    total_patch_chars: int
    max_files: int
    max_patch_chars_per_file: int
    max_total_patch_chars: int
    skipped_files: list[SkippedFile]
