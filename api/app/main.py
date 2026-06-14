from __future__ import annotations

import base64
import hashlib
import html as html_lib
import json
import mimetypes
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.agent_tokens import AgentTokenClaims, require_agent_scope
from app.config import WWW_DIR, Settings, get_settings


app = FastAPI(title="Apartment Gate")
BANNER_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "vendor"
    / "federated-banner"
    / "dist"
    / "browser"
    / "federated-banner.iife.js"
)


def serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_key or "", salt="apartment-gate")


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def pkce_challenge(verifier: str) -> str:
    return b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def app_url(settings: Settings, path: str = "") -> str:
    suffix = path if path.startswith("/") or path == "" else f"/{path}"
    return f"{settings.normalized_app_base_path}{suffix}" or "/"


def oauth_auto_retry_cookie_name(settings: Settings) -> str:
    return f"{settings.oauth_state_cookie_name}_auto_retry"


def safe_next(settings: Settings, next_path: str | None) -> str:
    if not next_path:
        return app_url(settings, "/")
    if next_path.startswith(settings.normalized_app_base_path or "/"):
        return next_path
    if next_path.startswith("/") and not next_path.startswith("//"):
        return app_url(settings, next_path)
    return app_url(settings, "/")


def signed_cookie(
    value: str | None,
    settings: Settings,
    *,
    max_age_seconds: int,
) -> dict[str, object] | None:
    if not value:
        return None
    try:
        payload = serializer(settings).loads(value, max_age=max_age_seconds)
    except BadSignature:
        return None
    return payload if isinstance(payload, dict) else None


def clear_oauth_auto_retry_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(oauth_auto_retry_cookie_name(settings), path=settings.normalized_app_base_path or "/")


def oauth_state_retry_redirect(request: Request, settings: Settings) -> RedirectResponse:
    retry_cookie = oauth_auto_retry_cookie_name(settings)
    if request.cookies.get(retry_cookie) == "1":
        response = RedirectResponse(app_url(settings, "/?oauth_error=oauth_state"), status_code=302)
        clear_oauth_auto_retry_cookie(response, settings)
        response.delete_cookie(settings.oauth_state_cookie_name, path=settings.normalized_app_base_path or "/")
        return response

    response = RedirectResponse(
        app_url(settings, f"/auth/oauth/login?{urlencode({'next': app_url(settings, '/')})}"),
        status_code=302,
    )
    response.set_cookie(
        retry_cookie,
        "1",
        max_age=60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=settings.normalized_app_base_path or "/",
    )
    response.delete_cookie(settings.oauth_state_cookie_name, path=settings.normalized_app_base_path or "/")
    return response


def require_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    payload = signed_cookie(
        request.cookies.get(settings.session_cookie_name),
        settings,
        max_age_seconds=settings.session_duration_minutes * 60,
    )
    if payload and isinstance(payload.get("sub"), str):
        return payload
    raise HTTPException(status_code=307, headers={"Location": app_url(settings, f"/auth/oauth/login?{urlencode({'next': str(request.url.path)})}")})


def require_gatewise_settings(settings: Settings) -> None:
    if (
        not settings.gatewise_web_api_key
        or not settings.gatewise_refresh_token
        or not settings.gatewise_community_id
        or not settings.gatewise_right_gate_access_point_id
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gate provider credentials are not configured.",
        )


async def gatewise_access_token(settings: Settings) -> str:
    require_gatewise_settings(settings)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://securetoken.googleapis.com/v1/token",
                params={"key": settings.gatewise_web_api_key},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": settings.gatewise_refresh_token,
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Gate provider token request failed.",
        ) from error
    access_token = response.json().get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Gate provider token response was invalid.",
        )
    return access_token


async def open_gatewise_access_point(settings: Settings, access_point_id: str) -> int:
    access_token = await gatewise_access_token(settings)
    base_url = settings.gatewise_api_base_url.rstrip("/")
    url = (
        f"{base_url}/api/v1/user/community/{settings.gatewise_community_id}"
        f"/access_point/{access_point_id}/open"
    )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {access_token}",
                    "Cache-Control": "no-cache",
                },
                content="{}",
            )
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Gate provider open request failed.",
        ) from error
    if response.status_code < 200 or response.status_code >= 300:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Gate provider rejected open request.",
        )
    return response.status_code


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/agent/open-right-gate")
async def open_right_gate_for_agent(
    _: Annotated[AgentTokenClaims, Depends(require_agent_scope("apartment_gate.open_right_gate"))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    provider_status = await open_gatewise_access_point(
        settings,
        settings.gatewise_right_gate_access_point_id,
    )
    return {
        "status": "opened",
        "access_point": "right_gate",
        "provider_status": provider_status,
    }


@app.get("/auth/oauth/login")
def oauth_login(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    next: str | None = None,
) -> RedirectResponse:
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    next_path = safe_next(settings, next or request.headers.get("referer"))
    state_payload = {
        "state": state,
        "verifier": verifier,
        "next": next_path,
        "created_at": datetime.now(tz=UTC).isoformat(),
    }
    params = {
        "response_type": "code",
        "client_id": settings.oauth_client_id,
        "redirect_uri": settings.oauth_redirect_uri,
        "scope": settings.oauth_scope,
        "state": state,
        "code_challenge": pkce_challenge(verifier),
        "code_challenge_method": "S256",
    }
    response = RedirectResponse(f"{settings.normalized_auth_base_url}/oauth/authorize?{urlencode(params)}", status_code=302)
    response.set_cookie(
        settings.oauth_state_cookie_name,
        serializer(settings).dumps(state_payload),
        max_age=600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=settings.normalized_app_base_path or "/",
    )
    return response


@app.get("/auth/oauth/callback")
async def oauth_callback(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    state_cookie = request.cookies.get(settings.oauth_state_cookie_name)
    state_payload = signed_cookie(state_cookie, settings, max_age_seconds=600)
    if not code or not state or not state_payload or state_payload.get("state") != state:
        return oauth_state_retry_redirect(request, settings)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token_response = await client.post(
                f"{settings.normalized_oauth_server_base_url}/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.oauth_client_id,
                    "code": code,
                    "redirect_uri": settings.oauth_redirect_uri,
                    "code_verifier": state_payload["verifier"],
                },
            )
            token_response.raise_for_status()
            access_token = token_response.json()["access_token"]
            userinfo_response = await client.get(
                f"{settings.normalized_oauth_server_base_url}/oauth/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            userinfo_response.raise_for_status()
            userinfo = userinfo_response.json()
    except Exception:
        response = RedirectResponse(app_url(settings, "/?oauth_error=oauth_failed"), status_code=302)
        response.delete_cookie(settings.oauth_state_cookie_name, path=settings.normalized_app_base_path or "/")
        clear_oauth_auto_retry_cookie(response, settings)
        return response

    response = RedirectResponse(str(state_payload.get("next") or app_url(settings, "/")), status_code=302)
    response.delete_cookie(settings.oauth_state_cookie_name, path=settings.normalized_app_base_path or "/")
    clear_oauth_auto_retry_cookie(response, settings)
    response.set_cookie(
        settings.session_cookie_name,
        serializer(settings).dumps(
            {
                "sub": str(userinfo.get("sub") or ""),
                "preferred_username": str(userinfo.get("preferred_username") or ""),
                "name": str(userinfo.get("name") or ""),
            }
        ),
        max_age=settings.session_duration_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=settings.normalized_app_base_path or "/",
    )
    return response


@app.get("/auth/logout")
def logout(settings: Annotated[Settings, Depends(get_settings)]) -> RedirectResponse:
    response = RedirectResponse(app_url(settings, "/"), status_code=302)
    response.delete_cookie(settings.session_cookie_name, path=settings.normalized_app_base_path or "/")
    return response


@app.get("/manifest.json")
def manifest(
    _: Annotated[dict[str, object], Depends(require_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    base = settings.normalized_app_base_path or ""
    payload = {
        "name": "Apartment Gate",
        "short_name": "Gate",
        "description": "Apartment gate controls",
        "start_url": f"{base}/",
        "scope": f"{base}/",
        "display": "standalone",
        "background_color": "#0b0f14",
        "theme_color": "#0b0f14",
        "orientation": "any",
        "icons": [
            {"src": f"{base}/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": f"{base}/static/icons/icon-192-maskable.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
            {"src": f"{base}/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": f"{base}/static/icons/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "categories": ["utilities"],
        "lang": "en",
        "dir": "ltr",
    }
    return Response(json.dumps(payload), media_type="application/manifest+json")


@app.get("/")
def index(
    user: Annotated[dict[str, object], Depends(require_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HTMLResponse:
    template = (WWW_DIR / "index.html").read_text(encoding="utf-8")
    base = settings.normalized_app_base_path or ""
    display_name = str(user.get("name") or user.get("preferred_username") or "Account")
    banner_markup = f"""
  <ghwiz-federated-banner
    id="federated-banner"
    app-name="Apartment Gate"
    app-url="{html_lib.escape(base or '/', quote=True)}"
    current-app-slug="apartment-gate"
    account-settings-url="{html_lib.escape(settings.account_settings_url, quote=True)}"
  ></ghwiz-federated-banner>
  <script>
    const federatedBanner = document.querySelector("#federated-banner");
    if (federatedBanner) {{
      federatedBanner.sites = {json.dumps(settings.federated_banner_sites)};
      federatedBanner.user = {json.dumps({"displayName": display_name, "username": str(user.get("preferred_username") or "")})};
      federatedBanner.addEventListener("federated-banner-action", (event) => {{
        if (event.detail?.action === "sign-out") {{
          window.location.assign("{html_lib.escape(base or '', quote=True)}/auth/logout");
        }}
      }});
    }}
  </script>
"""
    html = (
        template.replace("%WEB_API_KEY%", settings.gatewise_web_api_key)
        .replace("%REFRESH_TOKEN%", settings.gatewise_refresh_token)
        .replace("/gate/", f"{base}/")
        .replace("/gate/manifest.json", f"{base}/manifest.json")
        .replace("community/2524/", f"community/{settings.gatewise_community_id}/")
        .replace("</head>", f'  <script src="{base}/static/federated-banner.js"></script>\n</head>')
        .replace("<body>", f"<body>{banner_markup}")
    )
    return HTMLResponse(html)


@app.get("/static/{asset_path:path}")
def static_asset(
    asset_path: str,
    _: Annotated[dict[str, object], Depends(require_user)],
) -> Response:
    if asset_path == "federated-banner.js":
        if not BANNER_SCRIPT_PATH.is_file():
            raise HTTPException(status_code=404)
        return Response(BANNER_SCRIPT_PATH.read_bytes(), media_type="text/javascript")
    root = (WWW_DIR / "static").resolve()
    path = (root / asset_path).resolve()
    if root not in path.parents and path != root:
        raise HTTPException(status_code=404)
    if not path.is_file():
        raise HTTPException(status_code=404)
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return Response(path.read_bytes(), media_type=media_type)
