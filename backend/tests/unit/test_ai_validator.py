import json
import pytest
from app.schemas.finding import AnalysisFile
from app.services.diff_parser import parse_diff, DiffParseError
from app.services.finding_validator import FindingValidator, ReviewedFile
from app.services.report_service import ReportService

BASE = dict(file_path="a.py", line_number=2, source="ai", category="shell_injection",
 severity="high", title="Unsafe shell", description="User input reaches shell", suggestion="Use argv")
FILES = {"a.py": ReviewedFile(3, frozenset({2}))}


@pytest.mark.parametrize("change,reason", [
 ({"file_path":"other.py"},"unknown_file"), ({"line_number":0},"invalid_schema"),
 ({"line_number":True},"invalid_schema"), ({"line_number":4},"invalid_line_number"),
 ({"line_number":1},"outside_reviewed_changes"), ({"severity":"critical"},"invalid_schema"),
 ({"description":"x"*4001},"invalid_schema"), ({"title":None},"invalid_schema")])
def test_reject(change,reason):
 accepted,rejected=FindingValidator().validate([{**BASE,**change}],FILES)
 assert not accepted
 assert rejected==[{"index":0,"reason":reason}]


def test_missing_fields_and_valid_sibling():
 accepted,rejected=FindingValidator().validate([{},BASE],FILES)
 assert accepted[0][0]==1
 assert rejected[0]["index"]==0


@pytest.mark.parametrize("raw", ["not json", "[]", '{}', '{"findings":{}}'])
def test_invalid_json_or_envelope(raw):
 with pytest.raises(ValueError): FindingValidator().parse_response(raw)


def test_parse_valid():
 assert FindingValidator().parse_response(json.dumps({"findings":[BASE]}))==[BASE]
