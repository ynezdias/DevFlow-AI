import hashlib
import hmac
import json

from fastapi import APIRouter, HTTPException, Request

from app.config import settings

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
async def github_webhook(request: Request):
    raw_body = await request.body()
    verify_signature(raw_body, request.headers.get("X-Hub-Signature-256"))

    # Authenticate the exact bytes before decoding or trusting the payload.
    try:
        payload = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid JSON payload.")
    if not isinstance(payload, dict):
        raise HTTPException(400, "Expected a JSON object.")

    # Event-specific processing and review creation will be added separately.
    return {"status": "verified"}
