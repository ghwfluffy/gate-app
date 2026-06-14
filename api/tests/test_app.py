from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app, serializer


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
    assert "/gate/static/federated-banner.js" in response.text
