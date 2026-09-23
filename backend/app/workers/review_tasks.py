from datetime import datetime, timezone
from uuid import UUID

from celery.utils.log import get_task_logger
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ReviewJob
from app.services.github_service import GitHubService, GitHubError, StalePullRequest
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="app.workers.review_tasks.process_review")
def process_review(review_id: str):
    with SessionLocal.begin() as db:
        review = db.scalar(select(ReviewJob).where(ReviewJob.id == UUID(review_id)).with_for_update())
        if review is None:
            return {"status": "missing"}
        if review.status != "queued":
            return {"status": "skipped", "review_id": review_id}
        review.status = "processing"
        review.started_at = datetime.now(timezone.utc)
        review.attempt_count += 1
        installation_id, repository, number, sha = (review.installation_id, review.repository_name,
                                                   review.pull_request_number, review.head_sha)

    # No database transaction or row lock is held during network requests.
    files, error, status = None, None, "completed"
    try:
        if not installation_id:
            raise GitHubError("missing_installation_id")
        with GitHubService(installation_id) as github:
            files = github.get_review_files(repository, number, sha)
    except StalePullRequest:
        status, error = "superseded", "pull_request_changed"
    except GitHubError as exc:
        status, error = "failed", str(exc)
    except Exception:
        status, error = "failed", "unexpected_retrieval_error"

    with SessionLocal.begin() as db:
        review = db.get(ReviewJob, UUID(review_id))
        review.status = status
        review.changed_files = files
        review.error_code = error
        review.completed_at = datetime.now(timezone.utc)
    logger.info("Review retrieval review_id=%s status=%s files=%s error=%s",
                review_id, status, len(files) if files is not None else 0, error)
    return {"status": status, "review_id": review_id, "file_count": len(files) if files is not None else 0}
