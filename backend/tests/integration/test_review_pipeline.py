from tests.support import *

pytestmark = pytest.mark.usefixtures("database", "publisher", "webhook_secret")

@pytest.mark.parametrize("action", ["opened", "synchronize", "reopened"])
def test_supported_action_extracts_target(action):
    response = send_event(pr_payload(action))
    assert response.status_code == 202
    assert response.json()["review_id"]
    assert response.json() == {
        "review_id": response.json()["review_id"],
        "status": "accepted",
        "review_target": {
            "repository_id": 123, "repository_name": "ynezdias/devflow-test",
            "pull_request_number": 7, "head_sha": "a" * 40,
            "installation_id": 456, "base_sha": "c" * 40,
        },
    }


def test_synchronize_extracts_new_head():
    opened = send_event(pr_payload()).json()["review_target"]
    updated = send_event(pr_payload("synchronize", "b" * 40)).json()["review_target"]
    assert updated == {**opened, "head_sha": "b" * 40}


@pytest.mark.parametrize("action", ["closed", "edited", "labeled", None, []])
def test_unsupported_actions_ignore_without_requiring_target(action):
    response = send_event({"action": action})
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


@pytest.mark.parametrize("event", ["ping", "push", "issues"])
def test_other_events_ignored(event):
    response = send_event(pr_payload(), event)
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


@pytest.mark.parametrize("path,value", [
    (("repository", "id"), None),
    (("repository", "full_name"), ""),
    (("pull_request", "number"), True),
    (("pull_request", "head", "sha"), "not-a-sha"),
    (("installation", "id"), None),
])
def test_invalid_target_returns_400(path, value):
    payload = pr_payload()
    node = payload
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    assert send_event(payload).status_code == 400


def test_ignored_event_still_requires_authentication():
    response = client.post("/api/webhooks/github", json={"action": "closed"}, headers={"X-GitHub-Event": "pull_request"})
    assert response.status_code == 401


def test_missing_event_header():
    assert send_event(pr_payload(), None).status_code == 400


def test_publication_task_persists_id_and_reuses_check(database, monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from uuid import UUID
    import app.workers.publication_tasks as publication
    review_id = send_event(pr_payload()).json()["review_id"]
    review = database.get(ReviewJob, UUID(review_id))
    review.status = "completed"
    review.changed_files = []
    review.scope_summary = {"report": {"review_id": review_id, "status": "completed",
        "findings": [], "analysis": {"static_analysis": "completed", "ai_analysis": "completed"}}}
    database.commit()
    @contextmanager
    def transaction():
        with database.begin():
            yield database
    monkeypatch.setattr(publication, "SessionLocal", SimpleNamespace(begin=transaction))
    github = Mock()
    github.__enter__ = Mock(return_value=github)
    github.__exit__ = Mock(return_value=False)
    github.get_pull_request.return_value = {"head": {"sha": "a"*40}}
    github.list_check_runs.return_value = []
    github.list_check_annotations.return_value = []
    github.create_check_run.return_value = {"id": 12345}
    monkeypatch.setattr(publication, "GitHubService", Mock(return_value=github))
    assert publication.publish_review.run(review_id) == {"status": "published"}
    assert publication.publish_review.run(review_id) == {"status": "published"}
    review = database.get(ReviewJob, UUID(review_id))
    assert review.github_check_run_id == 12345
    assert review.publication_status == "published"
    github.create_check_run.assert_called_once()
    assert github.update_check_run.call_count == 1


def test_permanent_github_error_not_retried(database,monkeypatch,reliability_job):
    from uuid import UUID
    review_id,tasks,github=reliability_job
    github.get_review_snapshot.side_effect=tasks.GitHubError("github_http_401")
    retry=Mock()
    monkeypatch.setattr(tasks.process_review,"retry",retry)
    with pytest.raises(tasks.GitHubError,match="github_http_401"):
        tasks.process_review.run(review_id)
    retry.assert_not_called()
    job=database.get(ReviewJob,UUID(review_id))
    assert job.status=="failed"
    assert job.last_error=="github_http_401"
    assert job.completed_at is not None


def test_mocked_complete_pipeline(database, monkeypatch, reliability_job):
    from app.schemas.finding import CodeFinding
    from uuid import UUID
    review_id, tasks, github = reliability_job
    monkeypatch.setattr(tasks.settings, "ai_enabled", True)
    finding = CodeFinding(file_path="app.py", line_number=1, source="ruff", category="same", severity="low", title="Fixture", description="Fixture issue")
    monkeypatch.setattr(tasks.StaticAnalyzer, "analyze", Mock(return_value=[finding]))
    ai = Mock()
    ai.analyze_files.return_value = ([finding.model_copy(update={"source":"ai"})], {"enabled":True,"skipped_files":[]})
    monkeypatch.setattr(tasks, "AIReviewer", Mock(return_value=ai))
    assert tasks.process_review.run(review_id)["status"] == "completed"
    report = client.get(f"/api/reviews/{review_id}/report").json()
    assert report["summary"]["total_findings"] == 1
    assert report["findings"][0]["sources"] == ["ai", "ruff"]
    assert len(report["original_findings"]) == 2
    assert database.get(ReviewJob,UUID(review_id)).status == "completed"


def test_valid_raw_unicode_payload():
    body = '{ "message": "café" }'.encode()
    response = client.post("/api/webhooks/github", content=body, headers=signed(body))
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
