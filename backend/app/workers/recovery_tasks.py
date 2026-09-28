"""PostgreSQL is the durable work queue; Redis is a delivery mechanism."""
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select, or_, and_
from app.db.session import SessionLocal
from app.models import ReviewJob
from app.workers.celery_app import celery_app
from app.config import settings

@celery_app.task(name="app.workers.recovery_tasks.recover_reviews")
def recover_reviews(queue=None, review_id=None):
    from app.workers.review_tasks import process_review
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        ids = db.scalars(select(ReviewJob.id).where(ReviewJob.id == UUID(review_id) if review_id else True, ReviewJob.installation_id.is_not(None), or_(
            and_(ReviewJob.status == "queued", or_(ReviewJob.next_attempt_at.is_(None), ReviewJob.next_attempt_at <= now)),
            and_(ReviewJob.status == "processing", or_(ReviewJob.lease_expires_at.is_(None), ReviewJob.lease_expires_at <= now))
        )).order_by(ReviewJob.created_at).limit(100)).all()
    sent = 0
    for pending_id in ids:
        try:
            process_review.apply_async(args=[str(pending_id)], **({"queue":queue} if queue else {}))
            sent += 1
        except Exception:
            break  # Intent remains in PostgreSQL; next sweep retries after Redis recovers.
    if settings.github_checks_enabled:
        from app.workers.publication_tasks import publish_review
        with SessionLocal() as db:
            publication_ids = db.scalars(select(ReviewJob.id).where(
                ReviewJob.id == UUID(review_id) if review_id else True,
                ReviewJob.status.in_(["completed", "failed", "superseded"]),
                ReviewJob.installation_id.is_not(None),
                or_(ReviewJob.publication_status.is_(None), ReviewJob.publication_status.in_([
                    "in_progress", "pending", "retry_pending", "enqueue_failed"])),
                or_(ReviewJob.next_publication_at.is_(None), ReviewJob.next_publication_at <= now)
            ).order_by(ReviewJob.created_at).limit(100)).all()
        for pending_id in publication_ids:
            try:
                publish_review.apply_async(args=[str(pending_id)], **({"queue":queue} if queue else {}))
            except Exception:
                break
    return {"dispatched": sent}
