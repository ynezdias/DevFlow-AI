"""Schema validation is separate from commit-specific location validation."""
import json
from dataclasses import dataclass
from pydantic import ConfigDict, Field, ValidationError
from app.schemas.finding import CodeFinding
from app.services.diff_parser import parse_diff


class ValidatedFinding(CodeFinding):
    model_config = ConfigDict(strict=True, extra="forbid")
    file_path: str = Field(min_length=1, max_length=1024)
    category: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=256)
    description: str = Field(min_length=1, max_length=4000)
    suggestion: str | None = Field(default=None, max_length=4000)


@dataclass(frozen=True)
class ReviewedFile:
    line_count: int
    changed_lines: frozenset[int]

    @classmethod
    def from_source(cls, source):
        return cls(len(source.content.splitlines()), frozenset(parse_diff(source.patch).added_lines))


class FindingValidator:
    def parse_response(self, raw: str) -> list:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            raise ValueError("invalid_json") from None
        if not isinstance(data, dict) or set(data) != {"findings"} or not isinstance(data["findings"], list):
            raise ValueError("invalid_response_envelope")
        return data["findings"]

    def validate(self, findings: list, files: dict[str, ReviewedFile]):
        accepted, rejected = [], []
        for index, raw in enumerate(findings):
            try:
                finding = ValidatedFinding.model_validate(raw)
            except ValidationError:
                rejected.append({"index": index, "reason": "invalid_schema"})
                continue
            file = files.get(finding.file_path)
            reason = None
            if file is None:
                reason = "unknown_file"
            elif finding.line_number > file.line_count:
                reason = "invalid_line_number"
            elif finding.line_number not in file.changed_lines:
                reason = "outside_reviewed_changes"
            if reason:
                rejected.append({"index": index, "reason": reason})
            else:
                accepted.append((index, finding))
        return accepted, rejected
