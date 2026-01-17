#!/usr/bin/env python3

"""
Catch-all reverse proxy that logs endpoint + payload, forwards to an upstream, and returns response.

Usage:
  pip install flask requests
  python3 proxy.py --upstream http://127.0.0.1:8080 --listen 0.0.0.0 --port 8080
"""

from __future__ import annotations

import argparse
import sys
from typing import Dict, Iterable, Tuple

import requests
from flask import Flask, Response, request, stream_with_context

from urllib.parse import urlparse


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "x-real-ip",
    "x-forwarded-for",
    "x-forwarded-proto",
}


def _filtered_headers(in_headers: Dict[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in in_headers.items():
        if k.lower() in HOP_BY_HOP_HEADERS:
            continue
        out[k] = v
    return out


def make_app(upstream: str, timeout: float) -> Flask:
    app = Flask(__name__)
    sess = requests.Session()

    @app.before_request
    def log_request() -> None:
        # Endpoint + payload logging
        sys.stdout.write("\n=== Incoming Request ===\n")
        sys.stdout.write(f"{request.remote_addr} -> {request.method} {request.full_path}\n")
        sys.stdout.write("--- Headers ---\n")
        for k, v in request.headers.items():
            sys.stdout.write(f"{k}: {v}\n")

        body = request.get_data(cache=False)  # raw bytes
        sys.stdout.write(f"--- Body ({len(body)} bytes) ---\n")
        if body:
            # Print as utf-8 if possible; otherwise hex preview
            try:
                sys.stdout.write(body.decode("utf-8", errors="replace") + "\n")
            except Exception:
                sys.stdout.write(body[:256].hex() + ("...\n" if len(body) > 256 else "\n"))
        sys.stdout.flush()

    @app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
    @app.route("/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
    def catch_all(path: str):
        # Build upstream URL
        # request.full_path includes query string and ends with '?' if empty query
        full_path = request.full_path
        if full_path.endswith("?"):
            full_path = full_path[:-1]
        upstream_url = upstream.rstrip("/") + "/" + path
        if request.query_string:
            upstream_url += "?" + request.query_string.decode("utf-8", errors="replace")

        # Copy headers (minus hop-by-hop); set Host to upstream host via requests
        headers = _filtered_headers(dict(request.headers))

        # Forward raw body
        data = request.get_data(cache=False)

        # Forward request to upstream
        upstream_resp = sess.request(
            method=request.method,
            url=upstream_url,
            headers=headers,
            data=data if data else None,
            cookies=request.cookies,
            allow_redirects=False,
            stream=True,
            timeout=timeout,
        )
        resp_headers = dict(upstream_resp.headers)

        # ---- LOG UPSTREAM RESPONSE (status/headers/body) ----
        sys.stdout.write("\n=== Upstream Response ===\n")
        sys.stdout.write(f"{upstream_resp.status_code} {upstream_resp.reason}\n")
        sys.stdout.write("--- Headers ---\n")
        for k, v in resp_headers.items():
            sys.stdout.write(f"{k}: {v}\n")

        # Peek at up to N bytes without breaking streaming to client
        MAX_DUMP = 64 * 1024  # 64KiB
        dumped = bytearray()
        it = upstream_resp.iter_content(chunk_size=8192)

        chunks = []
        try:
            for chunk in it:
                if not chunk:
                    continue
                chunks.append(chunk)
                dumped += chunk
                break
            else:
                first_chunk = b""
        except Exception as e:
            sys.stdout.write(f"\n[!] Error reading upstream body: {e}\n")
            first_chunk = b""
        finally:
            upstream_resp.close()

        sys.stdout.write(f"--- Body dump (up to {MAX_DUMP} bytes; got {len(dumped)} bytes) ---\n")
        if dumped:
            try:
                sys.stdout.write(dumped.decode("utf-8", errors="replace") + "\n")
            except Exception:
                sys.stdout.write(dumped[:256].hex() + ("...\n" if len(dumped) > 256 else "\n"))
        sys.stdout.flush()
        # ---- END LOG ----

        def generate():
            for chunk in chunks:
                yield chunk

        return Response(
            stream_with_context(generate()),
            status=upstream_resp.status_code,
            headers=resp_headers,
        )

    return app


def normalize_upstream(u: str) -> str:
    u = u.strip()
    if not u:
        raise ValueError("Upstream is empty")
    if "://" not in u:
        u = "https://" + u  # default to https if omitted
    p = urlparse(u)
    if not p.scheme or not p.netloc:
        raise ValueError(f"Invalid upstream: {u!r}")
    return u.rstrip("/")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--upstream", required=True, help="Upstream base URL, e.g. http://example.com:8080")
    p.add_argument("--listen", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--timeout", type=float, default=270.0)
    args = p.parse_args()

    app = make_app(normalize_upstream(args.upstream), args.timeout)
    # Flask dev server is fine for quick use; for production use gunicorn/uwsgi.
    app.run(host=args.listen, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
