from datetime import datetime, timezone
from uuid import UUID
import time

from celery.utils.log import get_task_logger
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ReviewJob
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="app.workers.review_tasks.process_review")
def process_review(review_id: str):
    # Scaffold only: no static analysis or LLM call yet. Keep this database-only
    # unit atomic; the row lock makes concurrent/redelivered messages harmless.
    with SessionLocal.begin() as db:
        review = db.scalar(select(ReviewJob).where(
            ReviewJob.id == UUID(review_id)
        ).with_for_update())
        if review is None:
            return {"status": "missing"}
        if review.status != "queued":
            return {"status": "skipped", "review_id": review_id}
        review.status = "processing"
        review.started_at = datetime.now(timezone.utc)
        review.attempt_count += 1
        logger.info("Review worker scaffold executed review_id=%s (analysis not implemented)", review_id)
        time.sleep(1)  # Simulated work only; no repository code or AI calls.
        review.status = "completed"
        review.completed_at = datetime.now(timezone.utc)
    return {"status": "completed", "review_id": review_id, "analysis": "not_implemented"}
