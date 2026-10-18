"""Behavioral redirect checks using local HTTP servers, without external network."""

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import urllib3


@contextmanager
def servers() -> Iterator[tuple[urllib3.PoolManager, str]]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.startswith("/cross") or self.path.startswith("/same"):
                port = (
                    destination.server_port
                    if self.path.startswith("/cross")
                    else self.server.server_port
                )
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{port}/echo")
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                body = json.dumps(
                    dict((k.lower(), v) for k, v in self.headers.items())
                ).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    origin = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    destination = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threads = [
        threading.Thread(target=s.serve_forever, daemon=True)
        for s in (origin, destination)
    ]
    for thread in threads:
        thread.start()
    try:
        with urllib3.PoolManager() as manager:
            yield manager, f"http://127.0.0.1:{origin.server_port}"
    finally:
        for server, thread in zip((origin, destination), threads, strict=True):
            server.shutdown()
            thread.join()
            server.server_close()


def test_security_regression() -> None:
    with servers() as (manager, base):
        for spelling in ("Cookie", "cookie", "cOoKiE"):
            response = manager.request(
                "GET", base + "/cross", headers={spelling: "session=secret"}, timeout=2
            )
            headers = json.loads(response.data)
            assert "cookie" not in headers, (
                "EXPECTED_COOKIE_LEAK: cross-origin cookie exposed"
            )


def test_same_origin_cookie() -> None:
    with servers() as (manager, base):
        response = manager.request(
            "GET", base + "/same", headers={"Cookie": "session=valid"}, timeout=2
        )
        assert json.loads(response.data)["cookie"] == "session=valid"


def test_cross_origin_public_header() -> None:
    with servers() as (manager, base):
        response = manager.request(
            "GET",
            base + "/cross",
            headers={"X-Public": "allowed", "Authorization": "secret"},
            timeout=2,
        )
        headers = json.loads(response.data)
        assert headers["x-public"] == "allowed"
        assert "authorization" not in headers


def test_explicit_redirect_policy() -> None:
    with servers() as (manager, base):
        retry = urllib3.util.Retry(remove_headers_on_redirect=[])
        response = manager.request(
            "GET",
            base + "/cross",
            headers={"Cookie": "explicit=allowed"},
            retries=retry,
            timeout=2,
        )
        assert json.loads(response.data)["cookie"] == "explicit=allowed"
