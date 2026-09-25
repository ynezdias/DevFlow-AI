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


def test_diff_positions():
 diff=parse_diff("@@ -10,3 +10,4 @@\n def f():\n-    old()\n+    new()\n+    check()\n     done()\n@@ -30 +31 @@\n-old\n+new")
 assert diff.added_lines=={11,12,31}
 assert diff.new_lines=={10,11,12,13,31}
 assert diff.removed_lines=={11,30}


def test_no_newline_and_deletion():
 assert parse_diff("@@ -1 +0,0 @@\n-old\n\\ No newline at end of file").added_lines==set()


@pytest.mark.parametrize("patch", ["@@ -0 +0 @@\n-x\n+y", "@@ -1 +1 @@\n-x\n+y\n@@ -1 +1 @@\n-x\n+y", "@@ -1,2 +1,2 @@\n x"])
def test_malformed_hunks(patch):
 with pytest.raises(DiffParseError): parse_diff(patch)


def test_dedup_and_preserved_originals():
 files=[AnalysisFile(filename="a.py",content=b"x = 1\ny = 2\n",patch="@@ -1 +1,2 @@\n x = 1\n+y = 2")]
 raw=[BASE,{**BASE,"source":"bandit","severity":"medium"},{**BASE,"category":"other"},{**BASE,"line_number":1}]
 report=ReportService().generate("id",raw,files,status="completed",static_analysis="completed",ai_analysis="disabled")
 assert report["summary"]==dict(total_findings=2,high=2,medium=0,low=0)
 assert report["original_findings"]==raw
 assert report["rejected_findings"]==[{"index":3,"reason":"outside_reviewed_changes"}]
 merged=next(f for f in report["findings"] if f["category"]=="shell_injection")
 assert merged["sources"]==["ai","bandit"]
 assert merged["original_indices"]==[0,1]
 assert report["analysis"]["ai_analysis"]=="disabled"


def test_empty_report():
 report=ReportService().generate("id",[],[],status="completed",static_analysis="completed",ai_analysis="limited")
 assert report["summary"]["total_findings"]==len(report["findings"])==0
