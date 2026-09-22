import hashlib
import hmac
import json
from uuid import uuid4

from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.db.session import engine, get_db
from app.models import ReviewJob, WebhookEvent

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.webhooks import verify_signature
from app.workers.review_tasks import process_review
from kombu.exceptions import OperationalError
from unittest.mock import Mock
from app.config import settings
from app.main import app

client = TestClient(app)
SECRET = "test-webhook-secret"


@pytest.fixture(autouse=True)
def publisher(monkeypatch):
    publish = Mock()
    monkeypatch.setattr(process_review, "apply_async", publish)
    return publish


@pytest.fixture(autouse=True)
def webhook_secret(monkeypatch):
    monkeypatch.setattr(settings, "github_webhook_secret", SecretStr(SECRET))


@pytest.fixture(autouse=True)
def database():
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            app.dependency_overrides[get_db] = lambda: session
            try:
                yield session
            finally:
                app.dependency_overrides.pop(get_db, None)
        transaction.rollback()


def signed(body):
    return {"X-GitHub-Delivery": str(uuid4()), "X-GitHub-Event": "ping", "X-Hub-Signature-256": "sha256=" + hmac.new(
        SECRET.encode(), body, hashlib.sha256
    ).hexdigest()}


def test_github_documented_signature(monkeypatch):
    monkeypatch.setattr(settings, "github_webhook_secret", SecretStr("It's a Secret to Everybody"))
    verify_signature(b"Hello, World!", "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17")


def test_valid_raw_unicode_payload():
    body = '{ "message": "café" }'.encode()
    response = client.post("/api/webhooks/github", content=body, headers=signed(body))
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


@pytest.mark.parametrize("signature", [None, "", "sha1=abc", "sha256=" + "0" * 64])
def test_invalid_signature_before_json_parsing(signature):
    headers = {} if signature is None else {"X-Hub-Signature-256": signature}
    response = client.post("/api/webhooks/github", content=b"not json", headers=headers)
    assert response.status_code == 401


def test_tampered_body():
    response = client.post("/api/webhooks/github", content=b'{"x":2}', headers=signed(b'{"x":1}'))
    assert response.status_code == 401


@pytest.mark.parametrize("body", [b"not json", b"[]", b"null"])
def test_authenticated_invalid_payload(body):
    response = client.post("/api/webhooks/github", content=body, headers=signed(body))
    assert response.status_code == 400


def test_unconfigured_secret_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "github_webhook_secret", SecretStr(""))
    response = client.post("/api/webhooks/github", content=b"{}", headers=signed(b"{}"))
    assert response.status_code == 503


def pr_payload(action="opened", sha="a" * 40):
    return {
        "action": action,
        "repository": {"id": 123, "full_name": "ynezdias/devflow-test"},
        "pull_request": {"number": 7, "head": {"sha": sha}},
        "installation": {"id": 456},
    }


def send_event(payload, event="pull_request", delivery=None):
    body = json.dumps(payload).encode()
    headers = signed(body)
    headers.pop("X-GitHub-Event", None)
    if delivery is not None:
        headers["X-GitHub-Delivery"] = delivery
    if event is not None:
        headers["X-GitHub-Event"] = event
    return client.post("/api/webhooks/github", content=body, headers=headers)


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
            "installation_id": 456,
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


def test_delivery_deduplicated(database):
    delivery = str(uuid4())
    first = send_event(pr_payload(), delivery=delivery)
    second = send_event(pr_payload(), delivery=delivery)
    assert first.status_code == 202
    assert second.json() == {"status": "duplicate"}
    assert database.scalar(select(func.count()).select_from(WebhookEvent).where(WebhookEvent.delivery_id == delivery)) == 1


def test_distinct_deliveries_same_commit(database):
    first = send_event(pr_payload()).json()
    second = send_event(pr_payload("reopened")).json()
    assert first["review_id"] == second["review_id"]
    assert database.scalar(select(func.count()).select_from(ReviewJob).where(
        ReviewJob.repository_name == "ynezdias/devflow-test",
        ReviewJob.pull_request_number == 7, ReviewJob.head_sha == "a" * 40,
    )) == 1


def test_ignored_delivery_persisted(database):
    delivery = str(uuid4())
    assert send_event({"action": "closed"}, delivery=delivery).json() == {"status": "ignored"}
    assert send_event({"action": "closed"}, delivery=delivery).json() == {"status": "duplicate"}
    assert database.get(WebhookEvent, delivery).status == "ignored"


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


def test_worker_redelivery_is_idempotent(database, monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from uuid import UUID
    import app.workers.review_tasks as tasks
    response = send_event(pr_payload())
    review_id = response.json()["review_id"]

    @contextmanager
    def transaction():
        with database.begin():
            yield database

    monkeypatch.setattr(tasks, "SessionLocal", SimpleNamespace(begin=transaction))
    assert tasks.process_review.run(review_id)["status"] == "completed"
    assert tasks.process_review.run(review_id)["status"] == "skipped"
    review = database.get(ReviewJob, UUID(review_id))
    assert review.attempt_count == 1
    assert review.started_at is not None
    assert review.completed_at >= review.started_at
