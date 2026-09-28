"""Isolated worker fixture: mocked GitHub, real DB/Redis/analyzers. No live API calls."""
import time
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import ReviewJob
from app.schemas.changed_file import PullRequestSnapshot
from app.workers.celery_app import celery_app
import app.workers.review_tasks as tasks

class FixtureGitHub:
    def __init__(self,*args): pass
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def get_review_snapshot(self,repo,number,sha):
        if not repo.startswith("local-crash-test/"):
            raise RuntimeError("fixture_repository_required")
        with SessionLocal() as db:
            job=db.scalar(select(ReviewJob).where(ReviewJob.repository_name==repo))
            attempt=job.attempt_count
        if attempt==1:
            time.sleep(120)  # Intentionally killed during this stage.
        return PullRequestSnapshot(github_repository_id=1,base_sha="b"*40,head_sha=sha,
            files=[dict(filename="fixture.py",status="added",additions=1,deletions=0,changes=1,
                        patch="@@ -0,0 +1 @@\n+import os")])
    def get_file_content(self,*args): return b"import os\n"

tasks.GitHubService=FixtureGitHub
celery_app.worker_main(["worker","--pool=prefork","--concurrency=1","--queues=crash-test","--loglevel=info"])
