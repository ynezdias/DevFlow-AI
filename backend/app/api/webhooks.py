import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models import ReviewJob, WebhookEvent
from app.schemas.webhook import PullRequestTarget

SUPPORTED_ACTIONS = {"opened", "synchronize", "reopened"}
logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def verify_signature(raw_body: bytes, signature: str | None) -> None:
    secret = settings.github_webhook_secret.get_secret_value()
    if not secret:
        raise HTTPException(503, "Webhook secret is not configured.")

    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    if not signature or not hmac.compare_digest(
        expected.encode("ascii"), signature.encode("utf-8")
    ):
        raise HTTPException(401, "Invalid webhook signature.")


@router.post("/github")
async def github_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    verify_signature(raw_body, request.headers.get("X-Hub-Signature-256"))

    # Authenticate the exact bytes before decoding or trusting the payload.
    try:
        payload = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid JSON payload.")
    if not isinstance(payload, dict):
        raise HTTPException(400, "Expected a JSON object.")

    delivery_id = request.headers.get("X-GitHub-Delivery", "").strip()
    event_type = request.headers.get("X-GitHub-Event", "").strip()
    if not delivery_id or len(delivery_id) > 255 or not event_type or len(event_type) > 100:
        raise HTTPException(400, "Missing or invalid webhook delivery headers.")
    action = payload.get("action")
    target = None
    if event_type == "pull_request" and isinstance(action, str) and action in SUPPORTED_ACTIONS:
        try:
            target = PullRequestTarget.model_validate(payload)
        except ValidationError:
            raise HTTPException(400, "Invalid pull request payload.")

    # Both uniqueness checks and the job insert commit together. A failure rolls
    # back the delivery claim, so a GitHub retry can safely try again.
    with db.begin():
        claimed = db.scalar(insert(WebhookEvent).values(
            delivery_id=delivery_id, event_type=event_type,
            action=action[:100] if isinstance(action, str) else None,
            status="processed" if target else "ignored",
        ).on_conflict_do_nothing(index_elements=[WebhookEvent.delivery_id])
            .returning(WebhookEvent.delivery_id))
        if claimed is None:
            return {"status": "duplicate"}
        if target is None:
            return {"status": "ignored"}
        review_id = db.scalar(insert(ReviewJob).values(
            repository_name=target.repository_name,
            pull_request_number=target.pull_request_number, head_sha=target.head_sha,
        ).on_conflict_do_nothing(constraint="uq_review_commit").returning(ReviewJob.id))
        if review_id is None:
            review_id = db.scalar(select(ReviewJob.id).where(
                ReviewJob.repository_name == target.repository_name,
                ReviewJob.pull_request_number == target.pull_request_number,
                ReviewJob.head_sha == target.head_sha,
            ))

    logger.info("GitHub webhook received event=%s action=%s repository=%s pr=%s sha=%s delivery=%s",
                event_type, action, target.repository_name, target.pull_request_number,
                target.head_sha, delivery_id)
    return {"status": "accepted", "review_id": str(review_id), "review_target": target.model_dump()}
