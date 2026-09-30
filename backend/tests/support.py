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


@pytest.fixture
def publisher(monkeypatch):
    publish = Mock()
    monkeypatch.setattr(process_review, "apply_async", publish)
    return publish


@pytest.fixture
def webhook_secret(monkeypatch):
    monkeypatch.setattr(settings, "github_webhook_secret", SecretStr(SECRET))


@pytest.fixture
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














def pr_payload(action="opened", sha="a" * 40):
    return {
        "action": action,
        "repository": {"id": 123, "full_name": "ynezdias/devflow-test"},
        "pull_request": {"number": 7, "head": {"sha": sha}, "base": {"sha": "c" * 40}},
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




































@pytest.fixture
def reliability_job(database, monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from app.schemas.changed_file import PullRequestSnapshot
    import app.workers.review_tasks as tasks
    monkeypatch.setattr(tasks.settings, "github_checks_enabled", False)
    monkeypatch.setattr(tasks.settings, "ai_enabled", False)
    review_id=send_event(pr_payload()).json()["review_id"]
    @contextmanager
    def transaction():
        with database.begin():
            yield database
    monkeypatch.setattr(tasks,"SessionLocal",SimpleNamespace(begin=transaction))
    github=Mock()
    github.__enter__=Mock(return_value=github)
    github.__exit__=Mock(return_value=False)
    github.get_review_snapshot.return_value=PullRequestSnapshot(github_repository_id=123,base_sha="c"*40,head_sha="a"*40,
        files=[dict(filename="app.py",status="added",additions=1,deletions=0,changes=1,patch="@@ -0,0 +1 @@\n+import os")])
    github.get_file_content.return_value=b"import os\n"
    monkeypatch.setattr(tasks,"GitHubService",Mock(return_value=github))
    return review_id,tasks,github
















