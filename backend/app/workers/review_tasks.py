from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
from time import perf_counter

from celery.utils.log import get_task_logger
from sqlalchemy import select, delete

from app.db.session import SessionLocal
from app.models import ReviewJob, Finding
from app.services.github_service import GitHubService, GitHubError, TemporaryGitHubError, StalePullRequest
from app.services.review_scope import select_review_files
from app.workers.celery_app import celery_app
from app.services.static_analyzer import StaticAnalyzer, StaticAnalysisError
from app.schemas.finding import AnalysisFile
from app.config import settings
from app.services.report_service import ReportService
from app.services.ai_reviewer import AIReviewer, AIReviewError, TemporaryAIError
from app.services.job_logging import log_stage, safe_error
from app.workers.publication_tasks import start_check, publish_review

logger = get_task_logger(__name__)


def finish(review_id, status, error=None, token=None, delay=0):
    with SessionLocal.begin() as db:
        review = db.scalar(select(ReviewJob).where(ReviewJob.id == UUID(review_id)).with_for_update())
        if token and review.lease_token != token:
            return
        review.lease_token = None
        review.lease_expires_at = None
        review.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay) if status == "queued" else None
        review.last_error = safe_error(error) if error else None
        log_stage(review, status, error=error)
        review.status = status
        review.error_code = error
        review.completed_at = datetime.now(timezone.utc) if status != "queued" else None
    if settings.github_checks_enabled and status in {"failed", "superseded"}:
        try:
            publish_review.delay(review_id)
        except Exception:
            with SessionLocal.begin() as db:
                db.get(ReviewJob, UUID(review_id)).publication_status = "enqueue_failed"



@celery_app.task(bind=True, max_retries=3, name="app.workers.review_tasks.process_review")
def process_review(self, review_id: str):
    with SessionLocal.begin() as db:
        review = db.scalar(select(ReviewJob).where(ReviewJob.id == UUID(review_id)).with_for_update())
        if review is None:
            return {"status": "missing"}
        now = datetime.now(timezone.utc)
        if review.status == "processing" and (review.lease_expires_at is None or review.lease_expires_at <= now):
            review.status = "queued"
            review.last_error = "worker_lease_expired"
        if review.next_attempt_at and review.next_attempt_at > now:
            return {"status": "deferred", "review_id": review_id}
        if review.status != "queued":
            if (settings.github_checks_enabled and review.status in {"completed", "failed"}
                    and (review.scope_summary or {}).get("report")):
                publish_review.delay(review_id)
            return {"status": "skipped", "review_id": review_id}
        if review.attempt_count >= 4:
            review.status, review.error_code = "failed", "retry_limit_exceeded"
            review.last_error = "retry_limit_exceeded"
            review.lease_token = None
            review.lease_expires_at = None
            review.next_attempt_at = None
            review.completed_at = datetime.now(timezone.utc)
            return {"status": "failed", "review_id": review_id}
        token = uuid4()
        review.lease_token = token
        review.lease_expires_at = now + timedelta(seconds=settings.review_task_limit_seconds + 30)
        review.next_attempt_at = None
        review.status = "processing"
        review.started_at = datetime.now(timezone.utc)
        queue_wait_seconds = (review.started_at - review.created_at).total_seconds()
        review.attempt_count += 1
        review.error_code = None
        log_stage(review, "started")
        installation_id, repository, number, sha, attempts = (
            review.installation_id, review.repository_name, review.pull_request_number,
            review.head_sha, review.attempt_count)

    if settings.github_checks_enabled:
        try:
            if start_check(review_id) == "superseded":
                return {"status": "superseded", "review_id": review_id}
        except Exception:
            with SessionLocal.begin() as db:
                db.get(ReviewJob, UUID(review_id)).publication_status = "failed"

    try:
        if not installation_id:
            raise GitHubError("missing_installation_id")
        with GitHubService(installation_id) as github:
            snapshot = github.get_review_snapshot(repository, number, sha)
            relevant_files, summary = select_review_files(snapshot.files)
            sources = [AnalysisFile(filename=file.filename,
                content=github.get_file_content(repository, file.filename, sha), patch=file.patch)
                for file in relevant_files]
        findings, component_errors = [], {}
        ai_transient = False
        static_start = perf_counter()
        static_status = "completed"
        try:
            findings.extend(StaticAnalyzer().analyze(sources))
        except Exception:
            static_status = "failed"
            component_errors["static_analysis"] = "static_analysis_failed"
        static_seconds = perf_counter() - static_start
        ai_start = perf_counter()
        ai_status = "disabled"
        summary.ai = {"enabled": settings.ai_enabled}
        if settings.ai_enabled:
            try:
                ai_findings, summary.ai = AIReviewer().analyze_files(repository, sources)
                findings.extend(ai_findings)
                ai_status = ("failed" if summary.ai.get("failed_files") else
                    "limited" if summary.ai.get("skipped_files") else "completed")
                ai_transient = any(f.get("retryable", False) for f in summary.ai.get("failed_files", []))
                if ai_status == "failed":
                    component_errors["ai_analysis"] = "ai_analysis_failed"
                summary.limited = summary.limited or ai_status in {"limited", "failed"}
            except Exception as exc:
                ai_transient = isinstance(exc, TemporaryAIError)
                ai_status = "failed"
                component_errors["ai_analysis"] = "ai_analysis_failed"
        ai_seconds = perf_counter() - ai_start if settings.ai_enabled else None
        retry_ai = ai_transient and attempts < 4 and self.request.retries < self.max_retries
        final_status = "queued" if retry_ai else "failed" if component_errors else "completed"
        summary.report = ReportService().generate(review_id, findings, sources,
            status=final_status, static_analysis=static_status, ai_analysis=ai_status)
        summary.report["component_errors"] = component_errors
        summary.report["measurements"] = {"queue_wait_seconds": queue_wait_seconds,
            "static_analysis_seconds": static_seconds, "ai_analysis_seconds": ai_seconds,
            "static_findings": sum(f.source != "ai" for f in findings),
            "ai_findings": sum(f.source == "ai" for f in findings)}
    except StalePullRequest:
        finish(review_id, "superseded", "pull_request_changed", token)
        return {"status": "superseded", "review_id": review_id}
    except TemporaryGitHubError as exc:
        if self.request.retries >= self.max_retries or attempts >= 4:
            finish(review_id, "failed", "github_retry_exhausted", token)
            raise
        # Bounded exponential backoff; honor GitHub's longer rate-limit delay.
        delay = max(30 * 2 ** (attempts - 1), exc.retry_after or 0)
        finish(review_id, "queued", safe_error(exc), token, delay)
        from celery.exceptions import Retry
        try:
            raise self.retry(exc=exc, countdown=delay)
        except Retry:
            raise
        except Exception:
            # The database deadline remains queued for the recovery sweep.
            # Losing Redis must not discard the durable retry intent.
            return {"status": "queued", "review_id": review_id}
    except Exception as exc:
        finish(review_id, "failed", safe_error(exc), token)
        raise (GitHubError(safe_error(exc)) if isinstance(exc, GitHubError) else RuntimeError(safe_error(exc))) from None

    with SessionLocal.begin() as db:
        review = db.scalar(select(ReviewJob).where(ReviewJob.id == UUID(review_id)).with_for_update())
        if review.lease_token != token:
            return {"status": "lease_lost", "review_id": review_id}
        review.lease_token = None
        review.lease_expires_at = None
        review.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=30 * 2 ** (attempts - 1)) if retry_ai else None
        review.github_repository_id = snapshot.github_repository_id
        review.base_sha = snapshot.base_sha
        review.changed_files = [file.model_dump() for file in relevant_files]
        summary.report["measurements"]["job_to_report_seconds"] = (
            datetime.now(timezone.utc) - review.created_at).total_seconds()
        review.scope_summary = summary.model_dump()
        db.execute(delete(Finding).where(Finding.review_job_id == UUID(review_id)))
        db.add_all([Finding(review_job_id=UUID(review_id), **finding.model_dump()) for finding in findings])
        review.status = final_status
        review.error_code = "analysis_incomplete" if component_errors else None
        review.last_error = "ai_transport_error" if ai_transient else review.error_code
        review.completed_at = None if retry_ai else datetime.now(timezone.utc)
        log_stage(review, "static_" + static_status, static_seconds, component_errors.get("static_analysis"))
        log_stage(review, "ai_" + ai_status, ai_seconds, component_errors.get("ai_analysis"))
        log_stage(review, "analysis_" + final_status, static_seconds + (ai_seconds or 0), review.last_error)
    if retry_ai:
        from celery.exceptions import Retry
        try:
            raise self.retry(exc=TemporaryAIError("ai_transport_error"), countdown=30 * 2 ** (attempts - 1))
        except Retry:
            raise
        except Exception:
            return {"status": "queued", "review_id": review_id}
    if settings.github_checks_enabled:
        try:
            publish_review.delay(review_id)
        except Exception:
            with SessionLocal.begin() as db:
                db.get(ReviewJob, UUID(review_id)).publication_status = "enqueue_failed"
    logger.info("Review scoped review_id=%s selected=%s skipped=%s limited=%s",
                review_id, len(relevant_files), len(summary.skipped_files), summary.limited)
    return {"status": final_status, "review_id": review_id,
            "file_count": len(relevant_files), "finding_count": len(findings), "limited": summary.limited}
