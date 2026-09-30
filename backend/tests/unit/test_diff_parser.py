import json
import pytest
from app.schemas.finding import AnalysisFile
from app.services.diff_parser import parse_diff, DiffParseError
from app.services.finding_validator import FindingValidator, ReviewedFile
from app.services.report_service import ReportService

BASE = dict(file_path="a.py", line_number=2, source="ai", category="shell_injection",
 severity="high", title="Unsafe shell", description="User input reaches shell", suggestion="Use argv")
FILES = {"a.py": ReviewedFile(3, frozenset({2}))}


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
