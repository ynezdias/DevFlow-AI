from uuid import UUID
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
            return {"status": review.publication_status}
    except Exception as exc:
        with SessionLocal.begin() as db:
            review = db.get(ReviewJob, UUID(review_id))
            if review:
                review.publication_status = "failed"
        if isinstance(exc, TemporaryGitHubError) and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=max(30 * 2 ** self.request.retries, exc.retry_after or 0))
        # Celery logs only a safe generic code, never token/provider response text.
        raise RuntimeError("github_publication_failed") from None
