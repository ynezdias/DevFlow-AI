import json
import time
from datetime import datetime, timezone, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from app.services.github_service import GitHubService, GitHubError, StalePullRequest


@pytest.fixture
def key_file(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = tmp_path / "test.pem"
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return path, key.public_key()


def service(key_file, handler):
    return GitHubService(456, app_id="123", private_key_path=str(key_file[0]), transport=httpx.MockTransport(handler))


def token_response():
    return httpx.Response(201, json={"token": "installation-test-token", "expires_at": (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()})


def test_jwt_exchange_pagination_and_missing_patch(key_file):
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path.endswith("access_tokens"):
            claims = jwt.decode(request.headers["Authorization"].split()[1], key_file[1], algorithms=["RS256"])
            assert claims["iss"] == "123"
            assert claims["iat"] <= time.time() and claims["exp"] <= time.time()+600
            return token_response()
        assert request.headers["Authorization"] == "Bearer installation-test-token"
        item = {"filename":"binary.png","status":"added","additions":0,"deletions":0,"changes":0}
        return httpx.Response(200, json=[item]*100 if request.url.params["page"] == "1" else [dict(item, filename="app.py", patch="@@ diff")])
    with service(key_file, handler) as github:
        files = github.get_pull_request_files("owner/repo", 7)
    assert len(files) == 101 and files[0]["patch"] is None and files[-1]["patch"] == "@@ diff"
    assert len(calls) == 3


def test_refresh_expired_token(key_file):
    tokens = []
    def handler(request):
        if request.url.path.endswith("access_tokens"):
            tokens.append(1)
            return token_response()
        return httpx.Response(200, json={})
    with service(key_file, handler) as github:
        github.get_pull_request("owner/repo", 7)
        github._expires = 0
        github.get_pull_request("owner/repo", 7)
    assert len(tokens) == 2


@pytest.mark.parametrize("status", [401,403,404,429,500])
def test_api_errors_are_safe(key_file, status):
    with service(key_file, lambda r: httpx.Response(status, json={"secret":"DO_NOT_EXPOSE"})) as github:
        with pytest.raises(GitHubError, match=f"^github_http_{status}$"):
            github.get_pull_request("owner/repo",7)


@pytest.mark.parametrize("mode", ["success", "stale", "changed_during_fetch", "too_large", "incomplete"])
def test_review_snapshot_validation(key_file, mode):
    reads = 0
    def handler(request):
        nonlocal reads
        if request.url.path.endswith("access_tokens"):
            return token_response()
        if request.url.path.endswith("/files"):
            return httpx.Response(200,json=[])
        reads += 1
        sha = "other" if mode == "stale" or (mode == "changed_during_fetch" and reads == 2) else "head"
        return httpx.Response(200,json={"head":{"sha":sha},"base":{"sha":"base"},"changed_files":3001 if mode=="too_large" else (1 if mode=="incomplete" else 0)})
    with service(key_file, handler) as github:
        if mode == "success":
            assert github.get_review_files("owner/repo",7,"head") == []
        else:
            with pytest.raises(StalePullRequest if mode in {"stale","changed_during_fetch"} else GitHubError):
                github.get_review_files("owner/repo",7,"head")


def test_unconfigured_app_fails_without_network():
    with GitHubService(456, app_id="", private_key_path="") as github:
        with pytest.raises(GitHubError, match="github_app_not_configured"):
            github.get_pull_request("owner/repo",7)


def test_content_and_check_helpers(key_file):
    def handler(request):
        if request.url.path.endswith("access_tokens"):
            return token_response()
        if request.method == "POST":
            assert json.loads(request.content)["head_sha"] == "head"
            return httpx.Response(201,json={"id":1})
        assert request.url.params["ref"] == "head"
        return httpx.Response(200,json={"encoding":"base64","content":"aGVsbG8="})
    with service(key_file, handler) as github:
        assert github.get_file_content("owner/repo","app.py","head") == b"hello"
        assert github.create_check_run("owner/repo",name="DevFlow",head_sha="head") == {"id":1}


def test_network_timeout_is_sanitized(key_file):
    def handler(request):
        raise httpx.ReadTimeout("private transport detail", request=request)
    with service(key_file, handler) as github:
        with pytest.raises(GitHubError, match="^github_unavailable$"):
            github.get_pull_request("owner/repo",7)
