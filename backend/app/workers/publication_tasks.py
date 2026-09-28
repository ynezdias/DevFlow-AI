from uuid import UUID
from datetime import datetime, timezone, timedelta
from app.config import settings
from app.services.job_logging import log_stage
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import ReviewJob
from app.services.github_service import GitHubService, TemporaryGitHubError
from app.services.github_publisher import GitHubPublisher
from app.workers.celery_app import celery_app


def start_check(review_id):
    with SessionLocal.begin() as db:
        review = db.scalar(select(ReviewJob).where(ReviewJob.id == UUID(review_id)).with_for_update())
        if not review:
            return "missing"
        with GitHubService(review.installation_id) as github:
            publisher = GitHubPublisher(github)
            if review.status == "superseded":
                publisher.supersede(review)
            else:
                publisher.create_check_run(review)
        return review.status


@celery_app.task(bind=True, max_retries=3, name="app.workers.publication_tasks.publish_review")
def publish_review(self, review_id):
    with SessionLocal.begin() as db:
        review = db.scalar(select(ReviewJob).where(ReviewJob.id == UUID(review_id)).with_for_update())
        if not review:
            return {"status": "missing"}
        if review.publication_status == "published":
            return {"status": "published"}
        now = datetime.now(timezone.utc)
        if review.next_publication_at and review.next_publication_at > now:
            return {"status": "deferred"}
        if review.publication_attempt_count >= 4:
            review.publication_status = "failed"
            return {"status": "failed"}
        review.publication_attempt_count += 1
        attempt = review.publication_attempt_count
        review.publication_status = "pending"
        review.next_publication_at = now + timedelta(seconds=settings.review_task_limit_seconds + 30)
        log_stage(review, "publication_started")
    try:
        # Commit the recovered/created remote ID before annotation publication.
        if start_check(review_id) in {"missing", "superseded"}:
            return {"status": "superseded"}
        with SessionLocal.begin() as db:
            review = db.scalar(select(ReviewJob).where(ReviewJob.id == UUID(review_id)).with_for_update())
            report = (review.scope_summary or {}).get("report")
            if not report and review.status == "failed":
                report = {"review_id": str(review.id), "status": "failed", "findings": [],
                    "analysis": {"static_analysis": "not_run", "ai_analysis": "not_run"}}
            if not report or review.status not in {"completed", "failed"}:
                return {"status": "not_ready"}
            with GitHubService(review.installation_id) as github:
                GitHubPublisher(github).update_check_run(review, report)
            review.next_publication_at = None
            log_stage(review, "publication_" + review.publication_status)
            return {"status": review.publication_status}
    except Exception as exc:
        with SessionLocal.begin() as db:
            review = db.get(ReviewJob, UUID(review_id))
            if review:
                retryable = isinstance(exc, TemporaryGitHubError) and attempt < 4
                review.publication_status = "retry_pending" if retryable else "failed"
                review.next_publication_at = datetime.now(timezone.utc) + timedelta(seconds=max(30 * 2 ** (attempt-1), exc.retry_after or 0)) if retryable else None
                log_stage(review, "publication_failed", error="processing_error")
        if isinstance(exc, TemporaryGitHubError) and self.request.retries < self.max_retries and attempt < 4:
            raise self.retry(exc=exc, countdown=max(30 * 2 ** self.request.retries, exc.retry_after or 0))
        # Celery logs only a safe generic code, never token/provider response text.
        raise RuntimeError("github_publication_failed") from None
