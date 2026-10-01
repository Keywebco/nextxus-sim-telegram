import httpx
import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("ROGER_SIM_TELEGRAM_TOKEN", "test-telegram-token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("SIM_BACKEND_URL", "https://roger-sim-api.onrender.com")
    monkeypatch.setenv("SIM_BACKEND_TOKEN", "test-backend-token")
    return TestClient(main.app)


def update(text="Hello", chat_id=123):
    return {"update_id": 1, "message": {"chat": {"id": chat_id}, "text": text}}


def http_mock(monkeypatch, backend_status=200, backend_body=None, telegram_status=200):
    calls = []

    def handle(request):
        calls.append(request)
        if request.url.host == "roger-sim-api.onrender.com":
            return httpx.Response(backend_status, json=backend_body if backend_body is not None else {
                "choices": [{"message": {"content": "Roger says hello"}}]
            })
        return httpx.Response(telegram_status, json={"ok": telegram_status == 200})

    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    return calls


def headers():
    return {"X-Telegram-Bot-Api-Secret-Token": "test-secret"}


def test_happy_path(configured, monkeypatch):
    calls = http_mock(monkeypatch)
    response = configured.post("/webhook", json=update(), headers=headers())
    assert response.status_code == 200
    assert len(calls) == 2
    assert str(calls[0].url) == "https://roger-sim-api.onrender.com/v1/chat/completions"
    assert calls[0].headers["Authorization"] == "Bearer test-backend-token"
    import json
    body = json.loads(calls[0].content)
    assert body["session_id"] == "123"
    assert body["messages"] == [{"role": "user", "content": "Hello"}]
    assert json.loads(calls[1].content) == {"chat_id": 123, "text": "Roger says hello"}


def test_unauthorized_and_ignored_updates(configured, monkeypatch):
    calls = http_mock(monkeypatch)
    assert configured.post("/webhook", json=update()).status_code == 403
    assert configured.post("/webhook", json={"update_id": 2}, headers=headers()).status_code == 200
    assert configured.post("/webhook", json={"message": {"chat": {"id": 123}, "photo": []}}, headers=headers()).status_code == 200
    assert not calls


def test_backend_failure_sends_fallback(configured, monkeypatch):
    calls = http_mock(monkeypatch, backend_status=503)
    assert configured.post("/webhook", json=update(), headers=headers()).status_code == 200
    import json
    assert json.loads(calls[1].content)["text"] == main.FALLBACK


def test_telegram_failure_retries_update(configured, monkeypatch):
    http_mock(monkeypatch, telegram_status=502)
    assert configured.post("/webhook", json=update(), headers=headers()).status_code == 502


def test_long_reply_is_split(configured, monkeypatch):
    calls = http_mock(monkeypatch, backend_body={"choices": [{"message": {"content": "a" * 4100}}]})
    assert configured.post("/webhook", json=update(), headers=headers()).status_code == 200
    import json
    assert [len(json.loads(call.content)["text"]) for call in calls[1:]] == [4096, 4]


def test_health(configured):
    assert configured.get("/health").json() == {"status": "ok"}
