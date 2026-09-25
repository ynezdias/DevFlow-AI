from datetime import datetime, timezone
from uuid import UUID

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
from app.services.ai_reviewer import AIReviewer, AIReviewError
from app.workers.publication_tasks import start_check, publish_review

logger = get_task_logger(__name__)


def finish(review_id, status, error=None):
    with SessionLocal.begin() as db:
        review = db.get(ReviewJob, UUID(review_id))
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
        if review.status != "queued":
            if (settings.github_checks_enabled and review.status in {"completed", "failed"}
                    and (review.scope_summary or {}).get("report")):
                publish_review.delay(review_id)
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
        static_status = "completed"
        try:
            findings.extend(StaticAnalyzer().analyze(sources))
        except Exception:
            static_status = "failed"
            component_errors["static_analysis"] = "static_analysis_failed"
        ai_status = "disabled"
        summary.ai = {"enabled": settings.ai_enabled}
        if settings.ai_enabled:
            try:
                ai_findings, summary.ai = AIReviewer().analyze_files(repository, sources)
                findings.extend(ai_findings)
                ai_status = ("failed" if summary.ai.get("failed_files") else
                    "limited" if summary.ai.get("skipped_files") else "completed")
                if ai_status == "failed":
                    component_errors["ai_analysis"] = "ai_analysis_failed"
                summary.limited = summary.limited or ai_status in {"limited", "failed"}
            except Exception:
                ai_status = "failed"
                component_errors["ai_analysis"] = "ai_analysis_failed"
        final_status = "failed" if component_errors else "completed"
        summary.report = ReportService().generate(review_id, findings, sources,
            status=final_status, static_analysis=static_status, ai_analysis=ai_status)
        summary.report["component_errors"] = component_errors
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
        finish(review_id, "failed", str(exc) if isinstance(exc, (GitHubError, StaticAnalysisError, AIReviewError)) else "unexpected_retrieval_error")
        raise

    with SessionLocal.begin() as db:
        review = db.get(ReviewJob, UUID(review_id))
        review.github_repository_id = snapshot.github_repository_id
        review.base_sha = snapshot.base_sha
        review.changed_files = [file.model_dump() for file in relevant_files]
        review.scope_summary = summary.model_dump()
        db.execute(delete(Finding).where(Finding.review_job_id == UUID(review_id)))
        db.add_all([Finding(review_job_id=UUID(review_id), **finding.model_dump()) for finding in findings])
        review.status = final_status
        review.error_code = "analysis_incomplete" if component_errors else None
        review.completed_at = datetime.now(timezone.utc)
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
