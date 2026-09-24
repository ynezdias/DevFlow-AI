from datetime import datetime, timezone
from uuid import UUID

from celery.utils.log import get_task_logger
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ReviewJob
from app.services.github_service import GitHubService, GitHubError, TemporaryGitHubError, StalePullRequest
from app.services.review_scope import select_review_files
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)


def finish(review_id, status, error=None):
    with SessionLocal.begin() as db:
        review = db.get(ReviewJob, UUID(review_id))
        review.status = status
        review.error_code = error
        review.completed_at = datetime.now(timezone.utc) if status != "queued" else None


@celery_app.task(bind=True, max_retries=3, name="app.workers.review_tasks.process_review")
def process_review(self, review_id: str):
    with SessionLocal.begin() as db:
        review = db.scalar(select(ReviewJob).where(ReviewJob.id == UUID(review_id)).with_for_update())
        if review is None:
            return {"status": "missing"}
        if review.status != "queued":
            return {"status": "skipped", "review_id": review_id}
        if review.attempt_count >= 4:
            review.status, review.error_code = "failed", "retry_limit_exceeded"
            review.completed_at = datetime.now(timezone.utc)
            return {"status": "failed", "review_id": review_id}
        review.status = "processing"
        review.started_at = datetime.now(timezone.utc)
        review.attempt_count += 1
        review.error_code = None
        installation_id, repository, number, sha, attempts = (
            review.installation_id, review.repository_name, review.pull_request_number,
            review.head_sha, review.attempt_count)

    try:
        if not installation_id:
            raise GitHubError("missing_installation_id")
        with GitHubService(installation_id) as github:
            snapshot = github.get_review_snapshot(repository, number, sha)
        relevant_files, summary = select_review_files(snapshot.files)
    except StalePullRequest:
        finish(review_id, "superseded", "pull_request_changed")
        return {"status": "superseded", "review_id": review_id}
    except TemporaryGitHubError as exc:
        if self.request.retries >= self.max_retries or attempts >= 4:
            finish(review_id, "failed", "github_retry_exhausted")
            raise
        finish(review_id, "queued", str(exc))
        # Bounded exponential backoff; honor GitHub's longer rate-limit delay.
        delay = max(30 * 2 ** self.request.retries, exc.retry_after or 0)
        from celery.exceptions import Retry
        try:
            raise self.retry(exc=exc, countdown=delay)
        except Retry:
            raise
        except Exception:
            finish(review_id, "failed", "retry_publish_failed")
            raise
    except Exception as exc:
        finish(review_id, "failed", str(exc) if isinstance(exc, GitHubError) else "unexpected_retrieval_error")
        raise

    with SessionLocal.begin() as db:
        review = db.get(ReviewJob, UUID(review_id))
        review.github_repository_id = snapshot.github_repository_id
        review.base_sha = snapshot.base_sha
        review.changed_files = [file.model_dump() for file in relevant_files]
        review.scope_summary = summary.model_dump()
        review.status = "completed"
        review.error_code = None
        review.completed_at = datetime.now(timezone.utc)
    logger.info("Review scoped review_id=%s selected=%s skipped=%s limited=%s",
                review_id, len(relevant_files), len(summary.skipped_files), summary.limited)
    return {"status": "completed", "review_id": review_id,
            "file_count": len(relevant_files), "limited": summary.limited}
