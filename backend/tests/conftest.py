import pytest
from app.config import settings

@pytest.fixture(autouse=True)
def no_paid_services(monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", False)
    monkeypatch.setattr(settings, "github_checks_enabled", False)


@pytest.fixture(autouse=True)
def forbid_live_provider_requests(monkeypatch):
    import httpx
    original = httpx.Client.send
    def send(client, request, *args, **kwargs):
        if request.url.host in {"api.github.com", "generativelanguage.googleapis.com"} and isinstance(client._transport, httpx.HTTPTransport):
            pytest.fail("Live provider access is forbidden in automated tests")
        return original(client, request, *args, **kwargs)
    monkeypatch.setattr(httpx.Client, "send", send)
