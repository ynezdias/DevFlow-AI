"""Explicit benchmark-only adapters; never imported by the normal worker."""
import os
from app.config import settings
from app.schemas.changed_file import PullRequestSnapshot
from app.schemas.finding import CodeFinding

SOURCE = "import os\n\ndef run(command):\n    os.system(command)\n"
PATCH = "@@ -0,0 +1,4 @@\n" + "\n".join("+" + line for line in SOURCE.splitlines())


class FixtureGitHub:
    def __init__(self, *args): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass

    def get_review_snapshot(self, repo, number, sha):
        return PullRequestSnapshot(github_repository_id=1, base_sha="b" * 40,
            head_sha=sha, files=[dict(filename="fixture.py", status="added",
                additions=4, deletions=0, changes=4, patch=PATCH)])

    def get_file_content(self, *args):
        return SOURCE.encode()


class MockReviewer:
    def analyze_files(self, repository, files):
        return [CodeFinding(file_path="fixture.py", line_number=4, source="ai",
            category="shell", severity="high", title="Deterministic benchmark fixture",
            description="Synthetic finding; no provider request was made.",
            suggestion="Use an argument list instead of a shell command.")], {
                "enabled": True, "mode": "mock", "reviewed_files": ["fixture.py"],
                "failed_files": [], "skipped_files": [], "usage": []}


def main():
    if settings.environment != "benchmark" or os.getenv("AI_REVIEW_MODE") != "mock":
        raise RuntimeError("Benchmark worker requires ENVIRONMENT=benchmark and AI_REVIEW_MODE=mock")
    if settings.github_checks_enabled or settings.gemini_api_key.get_secret_value():
        raise RuntimeError("Benchmark must not contain live provider credentials or publishing")
    from app.workers import review_tasks
    review_tasks.GitHubService = FixtureGitHub
    review_tasks.AIReviewer = MockReviewer
    review_tasks.celery_app.worker_main([
        "worker", "--loglevel=WARNING", "--concurrency=1", "--without-gossip", "--without-mingle"])


if __name__ == "__main__":
    main()
