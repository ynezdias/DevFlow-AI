from tests.support import *

pytestmark = pytest.mark.usefixtures("database", "publisher", "webhook_secret")

def test_failure_rolls_back_delivery_for_retry(database, monkeypatch):
    delivery = str(uuid4())
    original = database.scalar
    calls = 0

    def fail_review(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated review insert failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(database, "scalar", fail_review)
    with pytest.raises(RuntimeError, match="simulated"):
        send_event(pr_payload(), delivery=delivery)
    monkeypatch.setattr(database, "scalar", original)
    response = send_event(pr_payload(), delivery=delivery)
    assert response.json()["status"] == "accepted"


def test_queue_failure_can_redeliver(database, publisher):
    delivery = str(uuid4())
    publisher.side_effect = OperationalError("Redis unavailable")
    assert send_event(pr_payload(), delivery=delivery).status_code == 503
    publisher.side_effect = None
    assert send_event(pr_payload(), delivery=delivery).status_code == 202
    assert publisher.call_count == 2
    assert send_event(pr_payload(), delivery=delivery).json() == {"status": "duplicate"}
    assert publisher.call_count == 2
    assert database.get(WebhookEvent, delivery).status == "enqueued"


@pytest.mark.parametrize("ai_enabled", [False, True])
@pytest.mark.parametrize("outcome", ["completed", "failed", "superseded"])
def test_worker_redelivery_is_idempotent(database, monkeypatch, outcome, ai_enabled):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from uuid import UUID
    import app.workers.review_tasks as tasks
    monkeypatch.setattr(tasks.settings, "ai_enabled", ai_enabled)
    from app.schemas.finding import CodeFinding
    ai = Mock()
    ai.analyze_files.return_value = ([CodeFinding(file_path="app.py", line_number=1,
        source="ai", category="test", severity="low", title="Fixture", description="Fixture finding",
        suggestion="Fixture suggestion")], {"enabled": True, "skipped_files": []})
    monkeypatch.setattr(tasks, "AIReviewer", Mock(return_value=ai))
    response = send_event(pr_payload())
    review_id = response.json()["review_id"]

    @contextmanager
    def transaction():
        with database.begin():
            yield database

    monkeypatch.setattr(tasks, "SessionLocal", SimpleNamespace(begin=transaction))
    fake_github = Mock()
    fake_github.__enter__ = Mock(return_value=fake_github)
    fake_github.__exit__ = Mock(return_value=False)
    files = [{"filename": "app.py", "status": "modified", "additions": 1, "deletions": 0, "changes": 1, "patch": "@@ -0,0 +1 @@\n+import os"}]
    from app.schemas.changed_file import PullRequestSnapshot
    fake_github.get_file_content.return_value = b"import os\n"
    fake_github.get_review_snapshot.return_value = PullRequestSnapshot(github_repository_id=123, base_sha="c"*40, head_sha="a"*40, files=files + [{"filename":"image.png", "status":"added", "additions":0, "deletions":0, "changes":0}])
    if outcome == "failed":
        fake_github.get_review_snapshot.side_effect = tasks.GitHubError("github_http_403")
    elif outcome == "superseded":
        fake_github.get_review_snapshot.side_effect = tasks.StalePullRequest("head_changed")
    monkeypatch.setattr(tasks, "GitHubService", Mock(return_value=fake_github))
    if outcome == "failed":
        with pytest.raises(tasks.GitHubError):
            tasks.process_review.run(review_id)
    else:
        assert tasks.process_review.run(review_id)["status"] == outcome
    assert tasks.process_review.run(review_id)["status"] == "skipped"
    review = database.get(ReviewJob, UUID(review_id))
    assert review.changed_files == (files if outcome == "completed" else None)
    assert review.github_repository_id == 123
    assert review.base_sha == "c" * 40
    if outcome == "completed":
        assert review.scope_summary["limited"] is True
        assert review.scope_summary["skipped_files"][0]["filename"] == "image.png"
    assert review.installation_id == 456
    fake_github.get_review_snapshot.assert_called_once()
    from app.models import Finding
    saved = database.scalars(select(Finding).where(Finding.review_job_id == UUID(review_id))).all()
    if outcome == "completed":
        fake_github.get_file_content.assert_called_once_with("ynezdias/devflow-test", "app.py", "a"*40)
        assert len(saved) == (2 if ai_enabled else 1)
        static = next(f for f in saved if f.source == "ruff")
        assert (static.category, static.file_path, static.line_number) == ("F401", "app.py", 1)
        assert review.scope_summary["ai"]["enabled"] == ai_enabled
        assert ai.analyze_files.call_count == int(ai_enabled)
        response = client.get(f"/api/reviews/{review_id}/findings")
        assert response.status_code == 200
        assert response.json()[0]["review_job_id"] == review_id
        report = client.get(f"/api/reviews/{review_id}/report")
        assert report.status_code == 200
        data = report.json()
        assert data["summary"]["total_findings"] == len(data["findings"]) == len(saved)
        assert len(data["original_findings"]) == len(saved)
        assert data["analysis"]["ai_analysis"] == ("completed" if ai_enabled else "disabled")
    else:
        assert saved == []
    assert review.attempt_count == 1
    assert review.started_at is not None
    assert review.completed_at >= review.started_at


@pytest.mark.parametrize("scenario", ["retry", "exhausted", "publish_failed"])
def test_temporary_worker_failure(database, monkeypatch, scenario):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from uuid import UUID
    from celery.exceptions import Retry
    import app.workers.review_tasks as tasks
    review_id = send_event(pr_payload()).json()["review_id"]
    @contextmanager
    def transaction():
        with database.begin():
            yield database
    monkeypatch.setattr(tasks, "SessionLocal", SimpleNamespace(begin=transaction))
    github = Mock()
    github.__enter__ = Mock(return_value=github)
    github.__exit__ = Mock(return_value=False)
    github.get_review_snapshot.side_effect = tasks.TemporaryGitHubError("github_http_429", retry_after=120)
    monkeypatch.setattr(tasks, "GitHubService", Mock(return_value=github))
    retries = 3 if scenario == "exhausted" else 0
    tasks.process_review.push_request(retries=retries)
    retry = Mock(side_effect=RuntimeError("publish unavailable") if scenario == "publish_failed" else Retry())
    monkeypatch.setattr(tasks.process_review, "retry", retry)
    try:
        expected = tasks.TemporaryGitHubError if scenario == "exhausted" else (RuntimeError if scenario == "publish_failed" else Retry)
        if scenario == "publish_failed":
            assert tasks.process_review.run(review_id)["status"] == "queued"
        else:
            with pytest.raises(expected):
                tasks.process_review.run(review_id)
    finally:
        tasks.process_review.pop_request()
    job = database.get(ReviewJob, UUID(review_id))
    assert job.status == ("queued" if scenario in {"retry", "publish_failed"} else "failed")
    assert job.attempt_count == 1
    if scenario == "retry":
        assert retry.call_args.kwargs["countdown"] == 120
        assert job.completed_at is None
    if scenario == "exhausted":
        retry.assert_not_called()
        assert job.error_code == "github_retry_exhausted"


@pytest.mark.parametrize("static_fails,ai_fails", [(False, True), (True, False), (True, True)])
def test_partial_analysis_preserved(database, monkeypatch, static_fails, ai_fails):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from uuid import UUID
    from app.models import Finding
    from app.schemas.finding import CodeFinding
    from app.schemas.changed_file import PullRequestSnapshot
    import app.workers.review_tasks as tasks
    monkeypatch.setattr(tasks.settings, "ai_enabled", True)
    review_id = send_event(pr_payload()).json()["review_id"]
    @contextmanager
    def transaction():
        with database.begin():
            yield database
    monkeypatch.setattr(tasks, "SessionLocal", SimpleNamespace(begin=transaction))
    github = Mock()
    github.__enter__ = Mock(return_value=github)
    github.__exit__ = Mock(return_value=False)
    github.get_file_content.return_value = b"import os\n"
    github.get_review_snapshot.return_value = PullRequestSnapshot(
        github_repository_id=123, base_sha="c"*40, head_sha="a"*40,
        files=[dict(filename="app.py", status="added", additions=1, deletions=0,
                    changes=1, patch="@@ -0,0 +1 @@\n+import os")])
    monkeypatch.setattr(tasks, "GitHubService", Mock(return_value=github))
    if static_fails:
        monkeypatch.setattr(tasks.StaticAnalyzer, "analyze", Mock(side_effect=tasks.StaticAnalysisError("tool failed")))
    ai = Mock()
    if ai_fails:
        ai.analyze_files.side_effect = tasks.AIReviewError("ai_transport_error")
    else:
        ai.analyze_files.return_value = ([CodeFinding(file_path="app.py", line_number=1,
            source="ai", category="fixture", severity="low", title="Fixture", description="Fixture")],
            {"enabled": True, "skipped_files": []})
    monkeypatch.setattr(tasks, "AIReviewer", Mock(return_value=ai))
    assert tasks.process_review.run(review_id)["status"] == "failed"
    assert tasks.process_review.run(review_id)["status"] == "skipped"
    job = database.get(ReviewJob, UUID(review_id))
    assert job.status == "failed"
    assert job.error_code == "analysis_incomplete"
    report_response = client.get(f"/api/reviews/{review_id}/report")
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["status"] == "failed"
    assert report["analysis"] == {"static_analysis": "failed" if static_fails else "completed",
                                  "ai_analysis": "failed" if ai_fails else "completed"}
    count = int(not static_fails) + int(not ai_fails)
    assert report["summary"]["total_findings"] == len(report["findings"]) == count
    assert len(database.scalars(select(Finding).where(Finding.review_job_id == UUID(review_id))).all()) == count


@pytest.mark.parametrize("expired",[False,True])
def test_processing_claim_recovery(database,reliability_job,expired):
    from uuid import UUID
    from datetime import datetime,timezone,timedelta
    review_id,tasks,github=reliability_job
    job=database.get(ReviewJob,UUID(review_id))
    job.status="processing"
    job.attempt_count=1
    job.lease_token=uuid4()
    job.lease_expires_at=datetime.now(timezone.utc)+timedelta(seconds=-1 if expired else 60)
    database.commit()
    result=tasks.process_review.run(review_id)
    assert result["status"]==("completed" if expired else "skipped")
    job=database.get(ReviewJob,UUID(review_id))
    assert job.attempt_count==(2 if expired else 1)


def test_old_attempt_cannot_write(database,reliability_job):
    from uuid import UUID
    review_id,tasks,github=reliability_job
    snapshot=github.get_review_snapshot.return_value
    def steal(*args):
        job=database.get(ReviewJob,UUID(review_id))
        job.lease_token=uuid4()
        database.commit()
        return snapshot
    github.get_review_snapshot.side_effect=steal
    assert tasks.process_review.run(review_id)["status"]=="lease_lost"
    assert database.get(ReviewJob,UUID(review_id)).scope_summary is None


@pytest.mark.parametrize("attempts,permanent",[(0,False),(3,False),(0,True)])
def test_ai_retry_preserves_static_results(database,monkeypatch,reliability_job,attempts,permanent):
    from uuid import UUID
    from celery.exceptions import Retry
    from app.models import Finding
    review_id,tasks,github=reliability_job
    job=database.get(ReviewJob,UUID(review_id))
    job.attempt_count=attempts
    database.commit()
    monkeypatch.setattr(tasks.settings,"ai_enabled",True)
    ai=Mock()
    ai.analyze_files.side_effect=tasks.AIReviewError("ai_http_401") if permanent else tasks.TemporaryAIError("ai_transport_error")
    monkeypatch.setattr(tasks,"AIReviewer",Mock(return_value=ai))
    retry=Mock(side_effect=Retry())
    monkeypatch.setattr(tasks.process_review,"retry",retry)
    if attempts==0 and not permanent:
        with pytest.raises(Retry): tasks.process_review.run(review_id)
        assert retry.call_args.kwargs["countdown"]==30
    else:
        assert tasks.process_review.run(review_id)["status"]=="failed"
        retry.assert_not_called()
    job=database.get(ReviewJob,UUID(review_id))
    assert job.attempt_count==attempts+1
    assert job.last_error
    assert database.scalar(select(func.count()).select_from(Finding).where(Finding.review_job_id==job.id))==1


def test_deadline_prevents_early_duplicate(database,reliability_job):
    from uuid import UUID
    from datetime import datetime,timezone,timedelta
    review_id,tasks,github=reliability_job
    job=database.get(ReviewJob,UUID(review_id))
    job.next_attempt_at=datetime.now(timezone.utc)+timedelta(seconds=60)
    database.commit()
    assert tasks.process_review.run(review_id)["status"]=="deferred"
    github.get_review_snapshot.assert_not_called()


def test_structured_logs_do_not_emit_exception_secrets(caplog):
    from types import SimpleNamespace
    import logging,json
    from app.services.job_logging import log_stage
    with caplog.at_level(logging.INFO,logger="devflow.jobs"):
        log_stage(SimpleNamespace(id="id",repository_name="org/repo",pull_request_number=1,head_sha="sha"),
            "failed",1.5,RuntimeError("API_KEY=do-not-log-source-content"))
    record=json.loads(caplog.records[-1].message)
    assert set(record)=={"review_id","repository","pull_request","head_sha","worker","stage","duration","error"}
    assert record["error"]=="processing_error"
    assert "do-not-log" not in caplog.text


@pytest.mark.parametrize("due",[True,False])
def test_recovery_sweep_respects_deadline(database,monkeypatch,reliability_job,due):
    from uuid import UUID
    from datetime import datetime,timezone,timedelta
    from contextlib import nullcontext
    import app.workers.recovery_tasks as recovery
    review_id,tasks,github=reliability_job
    job=database.get(ReviewJob,UUID(review_id))
    job.next_attempt_at=datetime.now(timezone.utc)+timedelta(seconds=-1 if due else 60)
    database.commit()
    monkeypatch.setattr(recovery,"SessionLocal",lambda:nullcontext(database))
    publish=Mock()
    monkeypatch.setattr(tasks.process_review,"apply_async",publish)
    result=recovery.recover_reviews.run(review_id=review_id)
    assert result["dispatched"]==int(due)
    assert publish.call_count==int(due)
