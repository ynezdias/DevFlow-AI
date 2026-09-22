from pydantic import AliasPath, BaseModel, Field


class PullRequestTarget(BaseModel):
    repository_id: int = Field(strict=True, gt=0, validation_alias=AliasPath("repository", "id"))
    repository_name: str = Field(min_length=1, max_length=255, validation_alias=AliasPath("repository", "full_name"))
    pull_request_number: int = Field(strict=True, gt=0, validation_alias=AliasPath("pull_request", "number"))
    head_sha: str = Field(pattern=r"^[0-9a-fA-F]{40}$", validation_alias=AliasPath("pull_request", "head", "sha"))
    installation_id: int = Field(strict=True, gt=0, validation_alias=AliasPath("installation", "id"))
