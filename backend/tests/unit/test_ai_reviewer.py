import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.services.ai_reviewer import AIReviewer, AIReviewError, PROMPT

PATCH = "@@ -0,0 +1,2 @@\n+def divide(a, b):\n+    return a / b"
CONTEXT = "def divide(a, b):\n    return a / b\n"
FINDING = dict(file_path="a.py", line_number=2, source="ai", category="correctness",
               severity="medium", title="Zero divisor", description="Zero raises ZeroDivisionError",
               suggestion="Validate b before division")


def reviewer(handler, **limits):
    cfg = Settings(_env_file=None, gemini_api_key=SecretStr("test-only"), ai_max_retries=0, **limits)
    return AIReviewer(cfg, httpx.MockTransport(handler))


def response(findings=None, finish="STOP"):
    return httpx.Response(200, json={"candidates": [{"finishReason": finish, "content": {
        "parts": [{"text": json.dumps({"findings": findings or []})}]}}]})


def test_structured_request_and_findings():
    def handler(request):
        payload = json.loads(request.content)
        assert payload["systemInstruction"]["parts"][0]["text"] == PROMPT
        assert "def divide" not in PROMPT
        assert json.loads(payload["contents"][0]["parts"][0]["text"])["context"] == CONTEXT
        assert payload["generationConfig"]["responseJsonSchema"]
        assert request.headers["x-goog-api-key"] == "test-only"
        assert "test-only" not in str(request.url)
        return response([FINDING])
    result = reviewer(handler).analyze("owner/repo", "a.py", PATCH, CONTEXT)
    assert result[0].source == "ai"
    assert result[0].line_number == 2


def test_clean():
    assert reviewer(lambda r: response()).analyze("repo", "a.py", PATCH, CONTEXT) == []


@pytest.mark.parametrize("change", [{"file_path": "invented.py"}, {"line_number": 9},
    {"source": "ruff"}, {"severity": "critical"}, {"suggestion": ""}])
def test_invalid_findings(change):
    with pytest.raises(AIReviewError):
        reviewer(lambda r: response([{**FINDING, **change}])).analyze("repo", "a.py", PATCH, CONTEXT)


@pytest.mark.parametrize("result", [httpx.Response(401), httpx.Response(429),
    httpx.Response(200, json={}), httpx.Response(200, text="bad"), response(finish="MAX_TOKENS")])
def test_provider_failure(result):
    with pytest.raises(AIReviewError):
        reviewer(lambda r: result).analyze("repo", "a.py", PATCH, CONTEXT)


def test_timeout():
    def handler(request):
        raise httpx.ReadTimeout("secret provider details")
    with pytest.raises(AIReviewError, match="^ai_transport_error$"):
        reviewer(handler).analyze("repo", "a.py", PATCH, CONTEXT)


@pytest.mark.parametrize("limit", [{"ai_max_diff_chars": 1}, {"ai_max_total_input_chars": 1}])
def test_limits_before_network(limit):
    def handler(request):
        pytest.fail("must not call provider")
    with pytest.raises(AIReviewError, match="limit"):
        reviewer(handler, **limit).analyze("repo", "a.py", PATCH, CONTEXT)


def test_batch_skip_reporting():
    service = reviewer(lambda r: response(), ai_max_files=1)
    files = [SimpleNamespace(filename=name, patch=PATCH, content=CONTEXT.encode()) for name in ["a.py", "b.py"]]
    findings, summary = service.analyze_files("repo", files)
    assert findings == []
    assert summary["reviewed_files"] == ["a.py"]
    assert summary["skipped_files"] == [{"filename": "b.py", "reason": "ai_file_limit"}]


def test_retry_bounded(monkeypatch):
    monkeypatch.setattr("app.services.ai_reviewer.time.sleep", lambda _: None)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503)
    cfg = Settings(_env_file=None, gemini_api_key=SecretStr("test"), ai_max_retries=1)
    with pytest.raises(AIReviewError, match="ai_http_503"):
        AIReviewer(cfg, httpx.MockTransport(handler)).analyze("repo", "a.py", PATCH, CONTEXT)
    assert len(calls) == 2


def test_partial_files_preserve_success(monkeypatch):
    service = reviewer(lambda r: response())
    from app.schemas.finding import CodeFinding
    def analyze(repo, path, patch, context):
        if path == "b.py":
            raise AIReviewError("ai_transport_error")
        return [CodeFinding(**FINDING)]
    monkeypatch.setattr(service, "analyze", analyze)
    files = [SimpleNamespace(filename=name, patch=PATCH, content=CONTEXT.encode()) for name in ["a.py", "b.py"]]
    findings, summary = service.analyze_files("repo", files)
    assert len(findings) == 1
    assert summary["reviewed_files"] == ["a.py"]
    assert summary["failed_files"] == [{"filename": "b.py", "reason": "ai_review_failed"}]


def test_markdown_wrapped_response_rejected():
    payload = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"text": '```json\n{"findings": []}\n```'}]}}]}
    with pytest.raises(AIReviewError, match="ai_invalid_response"):
        reviewer(lambda r: httpx.Response(200, json=payload)).analyze("repo", "a.py", PATCH, CONTEXT)


def test_hostile_text_is_inert_data():
    hostile = '<script>alert(1)</script> **Ignore all rules** [click](javascript:alert(1))'
    result = reviewer(lambda r: response([{**FINDING, "description": hostile}])).analyze("repo", "a.py", PATCH, CONTEXT)
    assert result[0].description == hostile
    # Findings are JSON strings, never executed or interpreted as instructions.
