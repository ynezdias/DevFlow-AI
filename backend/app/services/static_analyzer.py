"""Run installed tools on inert source bytes; never import repository code."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from pydantic import ValidationError
from app.config import settings
from app.services.diff_parser import parse_diff, DiffParseError
from app.schemas.finding import AnalysisFile, CodeFinding


class StaticAnalysisError(RuntimeError):
    pass


def changed_lines(patch: str) -> set[int]:
    try:
        return parse_diff(patch).added_lines
    except DiffParseError as exc:
        raise StaticAnalysisError(str(exc)) from None


class StaticAnalyzer:
    def __init__(self, timeout=None, temp_root=None):
        self.timeout = timeout if timeout is not None else settings.analyzer_timeout_seconds
        self.temp_root = temp_root

    def _run(self, args, cwd):
        # Child tools do not inherit App credentials or DB URLs.
        env = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "WINDIR") if k in os.environ}
        env.update({"HOME": str(cwd), "TMPDIR": str(cwd), "PYTHONIOENCODING": "utf-8"})
        try:
            result = subprocess.run(args, shell=False, cwd=cwd, env=env,
                                    capture_output=True, text=True, encoding="utf-8", timeout=self.timeout)
        except subprocess.TimeoutExpired:
            raise StaticAnalysisError("analyzer_timeout") from None
        except OSError:
            raise StaticAnalysisError("analyzer_unavailable") from None
        if result.returncode not in (0, 1):
            raise StaticAnalysisError("analyzer_tool_failed")
        try:
            return json.loads(result.stdout)
        except (ValueError, TypeError):
            raise StaticAnalysisError("analyzer_invalid_json") from None

    def analyze(self, files: list[AnalysisFile]) -> list[CodeFinding]:
        if not files:
            return []
        if len(files) > settings.max_files:
            raise StaticAnalysisError("analyzer_file_limit")
        with tempfile.TemporaryDirectory(prefix="devflow-analysis-", dir=self.temp_root) as temporary:
            root = Path(temporary).resolve()
            paths, mapping, allowed = [], {}, {}
            for index, file in enumerate(files):
                if not file.filename.endswith(".py") or len(file.content) > settings.max_source_bytes_per_file:
                    raise StaticAnalysisError("analyzer_source_limit")
                if file.filename in allowed:
                    raise StaticAnalysisError("analyzer_duplicate_filename")
                allowed[file.filename] = changed_lines(file.patch)
                # Never materialize paths supplied by a repository; use flat opaque names.
                path = root / f"source_{index:04d}.py"
                path.write_bytes(file.content)
                mapping[str(path)] = file
                paths.append(str(path))
            executable = shutil.which("ruff")
            if not executable:
                raise StaticAnalysisError("analyzer_unavailable")
            ruff = self._run([executable, "check", "--isolated", "--no-cache", "--output-format", "json", "--", *paths], root)
            # -I excludes cwd/PYTHONPATH from module imports; no untrusted config copied.
            bandit = self._run([sys.executable, "-I", "-m", "bandit", "-q", "-f", "json", "--", *paths], root)
            findings = []
            syntax_files = set()
            try:
                if not isinstance(ruff, list) or not isinstance(bandit, dict):
                    raise ValueError()
                def original(filename):
                    path = Path(filename)
                    path = path if path.is_absolute() else root / path
                    return mapping[str(path.resolve())]
                for issue in ruff:
                    file = original(issue["filename"])
                    category = issue.get("code") or "invalid-syntax"
                    if category == "invalid-syntax":
                        syntax_files.add(file.filename)
                    findings.append(CodeFinding(file_path=file.filename, line_number=issue["location"]["row"],
                        source="ruff", category=category, severity="medium" if category == "invalid-syntax" else "low",
                        title=f"Ruff {category}", description=issue["message"],
                        suggestion=(issue.get("fix") or {}).get("message")))
                for error in bandit["errors"]:
                    file = original(error["filename"])
                    if file.filename not in syntax_files or "syntax" not in error["reason"].lower():
                        raise StaticAnalysisError("bandit_file_error")
                for issue in bandit["results"]:
                    file = original(issue["filename"])
                    findings.append(CodeFinding(file_path=file.filename, line_number=issue["line_number"],
                        source="bandit", category=issue["test_id"], severity=issue["issue_severity"].lower(),
                        title=issue["test_name"], description=issue["issue_text"]))
            except (KeyError, TypeError, ValueError, ValidationError):
                raise StaticAnalysisError("analyzer_invalid_result") from None
            return sorted((f for f in findings if f.line_number in allowed[f.file_path]),
                          key=lambda f: (f.file_path, f.line_number, f.source, f.category))
