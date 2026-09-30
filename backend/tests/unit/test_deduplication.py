import json
import pytest
from app.schemas.finding import AnalysisFile
from app.services.diff_parser import parse_diff, DiffParseError
from app.services.finding_validator import FindingValidator, ReviewedFile
from app.services.report_service import ReportService

BASE = dict(file_path="a.py", line_number=2, source="ai", category="shell_injection",
 severity="high", title="Unsafe shell", description="User input reaches shell", suggestion="Use argv")
FILES = {"a.py": ReviewedFile(3, frozenset({2}))}


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
