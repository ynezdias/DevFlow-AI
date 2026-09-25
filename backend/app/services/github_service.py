"""GitHub App authentication and repository API operations (no PAT fallback)."""
import base64
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import httpx
import jwt

from app.config import settings
from app.schemas.changed_file import ChangedFile, PullRequestSnapshot
from pydantic import ValidationError


class GitHubError(RuntimeError):
    pass


class TemporaryGitHubError(GitHubError):
    def __init__(self, code, retry_after=None):
        super().__init__(code)
        self.retry_after = retry_after


class StalePullRequest(GitHubError):
    pass


class GitHubService:
    def __init__(self, installation_id: int, *, app_id=None, private_key_path=None, transport=None):
        self.installation_id = installation_id
        self.app_id = app_id if app_id is not None else settings.github_app_id
        self.private_key_path = private_key_path if private_key_path is not None else settings.github_private_key_path
        self.client = httpx.Client(base_url="https://api.github.com", timeout=20, transport=transport,
            headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"})
        self._token = None
        self._expires = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.client.close()

    def _request(self, method, path, **kwargs):
        try:
            response = self.client.request(method, path, **kwargs)
        except httpx.RequestError:
            raise TemporaryGitHubError("github_unavailable") from None
        if response.status_code in {408, 429} or response.status_code >= 500 or (
            response.status_code == 403 and (
                response.headers.get("x-ratelimit-remaining") == "0" or "retry-after" in response.headers
                or "rate limit" in response.text.lower()
            )
        ):
            delay = 60
            try:
                if "retry-after" in response.headers:
                    delay = max(delay, int(response.headers["retry-after"]))
                if response.headers.get("x-ratelimit-remaining") == "0":
                    delay = max(delay, int(response.headers.get("x-ratelimit-reset", "0")) - int(time.time()) + 1)
            except ValueError:
                pass
            raise TemporaryGitHubError(f"github_http_{response.status_code}", retry_after=delay)
        if response.status_code >= 400:
            # Do not expose response bodies, tokens, or private-key material.
            raise GitHubError(f"github_http_{response.status_code}")
        try:
            return response.json()
        except ValueError:
            raise GitHubError("github_invalid_response") from None

    def _installation_token(self):
        if self._token and time.time() < self._expires - 60:
            return self._token
        if not self.app_id or not self.private_key_path or not self.installation_id:
            raise GitHubError("github_app_not_configured")
        try:
            key = Path(self.private_key_path).read_bytes()
            now = int(time.time())
            signed = jwt.encode({"iat": now - 60, "exp": now + 540, "iss": str(self.app_id)}, key, algorithm="RS256")
        except (OSError, ValueError, jwt.PyJWTError):
            raise GitHubError("github_private_key_invalid") from None
        result = self._request("POST", f"/app/installations/{self.installation_id}/access_tokens",
                               headers={"Authorization": f"Bearer {signed}"})
        try:
            self._token = result["token"]
            self._expires = datetime.fromisoformat(result["expires_at"].replace("Z", "+00:00")).timestamp()
        except (KeyError, TypeError, ValueError):
            raise GitHubError("github_invalid_token_response") from None
        return self._token

    def _api(self, method, path, **kwargs):
        return self._request(method, path, headers={"Authorization": f"Bearer {self._installation_token()}"}, **kwargs)

    @staticmethod
    def _repo(repository):
        parts = repository.split("/")
        if len(parts) != 2 or any(not part or part in {".", ".."} for part in parts):
            raise GitHubError("invalid_repository")
        return "/repos/" + "/".join(quote(part, safe="") for part in parts)

    def get_pull_request(self, repository, number):
        return self._api("GET", f"{self._repo(repository)}/pulls/{number}")

    def get_pull_request_files(self, repository, number):
        files = []
        for page in range(1, 31):
            batch = self._api("GET", f"{self._repo(repository)}/pulls/{number}/files",
                              params={"per_page": 100, "page": page})
            if not isinstance(batch, list):
                raise GitHubError("github_invalid_files_response")
            for item in batch:
                try:
                    files.append(ChangedFile.model_validate(item))
                except (ValidationError, TypeError):
                    raise GitHubError("github_invalid_files_response") from None
            if len(batch) < 100:
                break
        return files

    def get_review_files(self, repository, number, head_sha):
        return self.get_review_snapshot(repository, number, head_sha).files

    def get_review_snapshot(self, repository, number, head_sha):
        before = self.get_pull_request(repository, number)
        if before["head"]["sha"] != head_sha:
            raise StalePullRequest("head_changed")
        if before["changed_files"] > 3000:
            raise GitHubError("github_file_limit_exceeded")
        files = self.get_pull_request_files(repository, number)
        after = self.get_pull_request(repository, number)
        if after["head"]["sha"] != head_sha or after["base"]["sha"] != before["base"]["sha"]:
            raise StalePullRequest("head_or_base_changed")
        if len(files) != after["changed_files"]:
            raise GitHubError("github_incomplete_files")
        return PullRequestSnapshot(github_repository_id=before["base"]["repo"]["id"],
                                   base_sha=before["base"]["sha"], head_sha=head_sha, files=files)

    def get_file_content(self, repository, path, ref):
        result = self._api("GET", f"{self._repo(repository)}/contents/{quote(path, safe='/')}", params={"ref": ref})
        if not isinstance(result, dict) or result.get("encoding") != "base64":
            raise GitHubError("github_content_unavailable")
        return base64.b64decode(result["content"])

    def create_check_run(self, repository, *, name, head_sha, **fields):
        return self._api("POST", f"{self._repo(repository)}/check-runs", json={**fields, "name": name, "head_sha": head_sha})


    def update_check_run(self, repository, check_id, **fields):
        return self._api("PATCH", f"{self._repo(repository)}/check-runs/{check_id}", json=fields)

    def list_check_runs(self, repository, sha):
        results = []
        for page in range(1, 101):
            batch = self._api("GET", f"{self._repo(repository)}/commits/{sha}/check-runs",
                params={"per_page": 100, "page": page, "filter": "all", "app_id": self.app_id})["check_runs"]
            results.extend(batch)
            if len(batch) < 100:
                return results
        raise GitHubError("github_check_pagination_limit")

    def list_check_annotations(self, repository, check_id):
        results = []
        for page in range(1, 101):
            batch = self._api("GET", f"{self._repo(repository)}/check-runs/{check_id}/annotations",
                params={"per_page": 100, "page": page})
            results.extend(batch)
            if len(batch) < 100:
                return results
        raise GitHubError("github_annotation_pagination_limit")
