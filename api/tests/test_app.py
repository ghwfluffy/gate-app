from __future__ import annotations

import json
from fastapi.testclient import TestClient

from app.agent_tokens import encode_agent_token
from app.config import Settings, get_settings
from app.main import app, serializer


class FakeGatewiseResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, object]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("provider failed")


class FakeGatewiseClient:
    calls: list[dict[str, object]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.args = args
        self.kwargs = kwargs

    async def __aenter__(self) -> FakeGatewiseClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, url: str, **kwargs: object) -> FakeGatewiseResponse:
        self.calls.append({"url": url, **kwargs})
        if "securetoken.googleapis.com" in url:
            return FakeGatewiseResponse({"access_token": "provider-access-token"})
        return FakeGatewiseResponse({"ok": True}, status_code=202)


def test_index_redirects_to_oauth_when_unauthenticated() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_env="test",
        app_base_path="/gate",
        public_url="http://testserver",
        auth_base_url="/ghwidx",
        session_key="test-secret",
    )
    try:
        with TestClient(app) as client:
            response = client.get("/", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 307
    assert response.headers["location"].startswith("/gate/auth/oauth/login")


def test_authenticated_manifest_uses_base_path() -> None:
    settings = Settings(
        app_env="test",
        app_base_path="/gate",
        public_url="http://testserver",
        auth_base_url="/ghwidx",
        session_key="test-secret",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    cookie = serializer(settings).dumps({"sub": "oauth:123", "preferred_username": "owner"})
    try:
        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, cookie)
            response = client.get("/manifest.json")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["start_url"] == "/gate/"
    assert payload["icons"][0]["src"] == "/gate/static/icons/icon-192.png"


def test_authenticated_index_includes_federated_banner() -> None:
    settings = Settings(
        app_env="test",
        app_base_path="/gate",
        public_url="http://testserver",
        auth_base_url="/ghwidx",
        session_key="test-secret",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    cookie = serializer(settings).dumps({"sub": "oauth:123", "preferred_username": "owner", "name": "Owner"})
    try:
        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, cookie)
            response = client.get("/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "<ghwiz-federated-banner" in response.text
    assert 'current-app-slug="apartment-gate"' in response.text
    assert 'account-settings-url="/ghwidx?tab=account-settings"' in response.text
    assert "/gate/static/federated-banner.js" in response.text


def test_configured_federated_inventory_replaces_legacy_partial_list() -> None:
    settings = Settings(
        app_env="test",
        federated_apps=json.dumps([
            {"slug": "notes", "name": "My Notes", "baseUrl": "/notes", "description": "Lists"},
            {"slug": "omni-dev", "name": "Omni Dev", "baseUrl": "/dev"},
        ]),
    )

    assert [site["slug"] for site in settings.federated_banner_sites] == ["notes", "omni-dev"]


def test_oauth_callback_retries_once_when_state_is_missing() -> None:
    settings = Settings(
        app_env="test",
        app_base_path="/gate",
        public_url="http://testserver",
        auth_base_url="/ghwidx",
        session_key="test-secret",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.get("/auth/oauth/callback?code=abc&state=missing", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 302
    assert response.headers["location"] == "/gate/auth/oauth/login?next=%2Fgate%2F"
    assert response.cookies.get(f"{settings.oauth_state_cookie_name}_auto_retry") == "1"


def test_oauth_callback_stops_retrying_after_one_missing_state() -> None:
    settings = Settings(
        app_env="test",
        app_base_path="/gate",
        public_url="http://testserver",
        auth_base_url="/ghwidx",
        session_key="test-secret",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            client.cookies.set(f"{settings.oauth_state_cookie_name}_auto_retry", "1")
            response = client.get("/auth/oauth/callback?code=abc&state=missing", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 302
    assert response.headers["location"] == "/gate/?oauth_error=oauth_state"


def test_agent_open_right_gate_requires_valid_agent_token() -> None:
    settings = Settings(
        app_env="test",
        app_base_path="/gate",
        public_url="http://testserver",
        auth_base_url="/ghwidx",
        session_key="test-secret",
        agent_integration_token_secret="test-agent-secret",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.post("/api/agent/open-right-gate")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_agent_open_right_gate_uses_configured_gatewise_access_point(monkeypatch) -> None:
    settings = Settings(
        app_env="test",
        app_base_path="/gate",
        public_url="http://testserver",
        auth_base_url="/ghwidx",
        session_key="test-secret",
        agent_integration_token_secret="test-agent-secret",
        gatewise_web_api_key="web-api-key",
        gatewise_refresh_token="refresh-token",
        gatewise_api_base_url="https://gatewise.example.test",
        gatewise_community_id="2524",
        gatewise_right_gate_access_point_id="right-gate-test-id",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    FakeGatewiseClient.calls = []
    monkeypatch.setattr("app.main.httpx.AsyncClient", FakeGatewiseClient)
    token = encode_agent_token(
        secret="test-agent-secret",
        subject="central-user",
        scope="apartment_gate.open_right_gate",
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/agent/open-right-gate",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "opened",
        "access_point": "right_gate",
        "provider_status": 202,
    }
    assert len(FakeGatewiseClient.calls) == 2
    assert FakeGatewiseClient.calls[0]["url"] == "https://securetoken.googleapis.com/v1/token"
    assert FakeGatewiseClient.calls[0]["params"] == {"key": "web-api-key"}
    assert FakeGatewiseClient.calls[1]["url"] == (
        "https://gatewise.example.test/api/v1/user/community/2524/access_point/right-gate-test-id/open"
    )
    assert FakeGatewiseClient.calls[1]["headers"] == {
        "Accept": "application/json",
        "Authorization": "Bearer provider-access-token",
        "Cache-Control": "no-cache",
    }
