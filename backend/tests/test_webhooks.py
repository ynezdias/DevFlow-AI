import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.webhooks import verify_signature
from app.config import settings
from app.main import app

client = TestClient(app)
SECRET = "test-webhook-secret"


@pytest.fixture(autouse=True)
def webhook_secret(monkeypatch):
    monkeypatch.setattr(settings, "github_webhook_secret", SecretStr(SECRET))


def signed(body):
    return {"X-Hub-Signature-256": "sha256=" + hmac.new(
        SECRET.encode(), body, hashlib.sha256
    ).hexdigest()}


def test_github_documented_signature(monkeypatch):
    monkeypatch.setattr(settings, "github_webhook_secret", SecretStr("It's a Secret to Everybody"))
    verify_signature(b"Hello, World!", "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17")


def test_valid_raw_unicode_payload():
    body = '{ "message": "café" }'.encode()
    response = client.post("/api/webhooks/github", content=body, headers=signed(body))
    assert response.status_code == 200
    assert response.json() == {"status": "verified"}


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
