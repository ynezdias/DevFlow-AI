"""Only explicit job identifiers and controlled error codes enter log records."""
import json
import logging
import re
import socket

logger = logging.getLogger("devflow.jobs")

def safe_error(error):
    code = str(error or "")
    allowed = {"missing_installation_id", "github_app_not_configured", "github_private_key_invalid",
        "github_invalid_response", "github_unavailable", "ai_transport_error", "ai_incomplete_response",
        "ai_invalid_response", "ai_missing_key", "analyzer_timeout", "analysis_incomplete",
        "worker_lease_expired", "retry_limit_exceeded", "github_retry_exhausted", "pull_request_changed"}
    return code if code in allowed or re.fullmatch(r"(?:github|ai)_http_[0-9]{3}", code) else "processing_error"

def log_stage(review, stage, duration=None, error=None):
    logger.info(json.dumps({"review_id":str(review.id), "repository":review.repository_name,
        "pull_request":review.pull_request_number, "head_sha":review.head_sha,
        "worker":socket.gethostname(), "stage":stage, "duration":duration,
        "error":safe_error(error) if error else None}, ensure_ascii=True))
