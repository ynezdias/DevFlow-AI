from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest
from app.schemas.finding import AnalysisFile, CodeFinding
from app.services.static_analyzer import StaticAnalyzer, StaticAnalysisError, changed_lines


def source(name, text, patch=None):
    lines = text.splitlines()
    patch = patch if patch is not None else f"@@ -0,0 +1,{len(lines)} @@\n" + "\n".join("+"+line for line in lines)
    return AnalysisFile(filename=name, content=text.encode(), patch=patch)


def test_clean_file(tmp_path):
    assert StaticAnalyzer(temp_root=tmp_path).analyze([source("clean.py", "def add(a, b):\n    return a + b\n")]) == []
    assert list(tmp_path.iterdir()) == []


def test_ruff_unused_import_has_original_path_and_line():
    findings = StaticAnalyzer().analyze([source("pkg/imports.py", "import os\n")])
    assert [(f.source, f.category, f.file_path, f.line_number) for f in findings] == [("ruff", "F401", "pkg/imports.py", 1)]
    assert all(isinstance(f, CodeFinding) for f in findings)


def test_bandit_command_execution_separate_fixture():
    findings = StaticAnalyzer().analyze([source("security.py", "import os\n\ndef run_command(command):\n    os.system(command)\n")])
    assert any(f.source == "bandit" and f.category == "B605" and f.line_number == 4 for f in findings)
    assert not any(f.category == "F401" for f in findings)


def test_preexisting_findings_are_not_reported():
    patch = "@@ -2 +2 @@\n-x = 1\n+x = 2"
    assert StaticAnalyzer().analyze([source("old.py", "import os\nx = 2\n", patch)]) == []


def test_malformed_python_returns_syntax_finding():
    findings = StaticAnalyzer().analyze([source("broken.py", "def broken(:\n    pass\n")])
    assert any(f.source == "ruff" and f.category == "invalid-syntax" and f.line_number == 1 for f in findings)


def test_diff_multiple_hunks_and_deletions():
    patch = "@@ -1,3 +1,3 @@\n same\n-old\n+new\n same\n@@ -9,0 +10,2 @@\n+first\n+second\n\\ No newline at end of file"
    assert changed_lines(patch) == {2, 10, 11}


@pytest.mark.parametrize("patch", ["", "@@ -0,0 +1,2 @@\n+only_one", "bad patch", "@@ invalid @@"])
def test_incomplete_diff_fails_explicitly(patch):
    with pytest.raises(StaticAnalysisError):
        changed_lines(patch)


@pytest.mark.parametrize("failure", ["timeout", "exit", "json", "missing", "shape"])
def test_tool_failure_and_cleanup(tmp_path, monkeypatch, failure):
    import app.services.static_analyzer as module
    def run(args, **kw):
        assert isinstance(args, list) and kw["shell"] is False
        assert kw["timeout"] == 1
        assert Path(kw["cwd"]).is_relative_to(tmp_path)
        assert "GITHUB_APP_ID" not in kw["env"]
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args, 1)
        if failure == "missing":
            raise FileNotFoundError()
        return subprocess.CompletedProcess(args, 2 if failure == "exit" else 0, "not json" if failure == "json" else "{}", "")
    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(StaticAnalysisError):
        StaticAnalyzer(timeout=1, temp_root=tmp_path).analyze([source("app.py", "x = 1\n")])
    assert list(tmp_path.iterdir()) == []


def test_repository_code_never_executes_and_paths_are_inert(tmp_path):
    marker = tmp_path / "executed.txt"
    code = f"open({str(marker)!r}, 'w').write('executed')\n"
    StaticAnalyzer(temp_root=tmp_path).analyze([source("../../escape.py", code)])
    assert not marker.exists()
    assert list(tmp_path.iterdir()) == []


def test_real_process_timeout_is_bounded(tmp_path):
    import sys
    with pytest.raises(StaticAnalysisError, match="analyzer_timeout"):
        StaticAnalyzer(timeout=0.05)._run([sys.executable, "-c", "import time; time.sleep(2)"], tmp_path)


def test_same_basename_keeps_distinct_paths():
    files = [source("one/app.py", "import os\n"), source("two/app.py", "import sys\n")]
    assert {f.file_path for f in StaticAnalyzer().analyze(files)} == {"one/app.py", "two/app.py"}
