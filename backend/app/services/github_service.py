"""GitHub App authentication and repository API operations (no PAT fallback)."""
import base64
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import httpx
import jwt

from app.config import settings


class GitHubError(RuntimeError):
    pass


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
            raise GitHubError("github_unavailable") from None
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
                    files.append({**{key: item[key] for key in
                        ("filename", "status", "additions", "deletions", "changes")}, "patch": item.get("patch")})
                except (KeyError, TypeError):
                    raise GitHubError("github_invalid_files_response") from None
            if len(batch) < 100:
                break
        return files

    def get_review_files(self, repository, number, head_sha):
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
        return files

    def get_file_content(self, repository, path, ref):
        result = self._api("GET", f"{self._repo(repository)}/contents/{quote(path, safe='/')}", params={"ref": ref})
        if not isinstance(result, dict) or result.get("encoding") != "base64":
            raise GitHubError("github_content_unavailable")
        return base64.b64decode(result["content"])

    def create_check_run(self, repository, *, name, head_sha, **fields):
        return self._api("POST", f"{self._repo(repository)}/check-runs", json={**fields, "name": name, "head_sha": head_sha})
