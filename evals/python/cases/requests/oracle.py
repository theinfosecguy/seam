"""Check proxy authorization using an in-memory recording transport."""

from typing import Any

import requests
from requests.adapters import BaseAdapter, HTTPAdapter

PROXY = "http://alice:secret@proxy.example:8080"
BASIC_AUTH = "Basic YWxpY2U6c2VjcmV0"


class RecordingTransport(BaseAdapter):
    def __init__(self, destination: str) -> None:
        self.destination = destination
        self.sent = []

    def send(
        self, request: requests.PreparedRequest, **kwargs: Any
    ) -> requests.Response:
        self.sent.append((request.copy(), kwargs.copy()))
        response = requests.Response()
        response.request = request
        response.url = request.url
        response._content = b""
        if len(self.sent) == 1:
            response.status_code = 302
            response.headers["Location"] = self.destination
        else:
            response.status_code = 200
        return response

    def close(self) -> None:
        pass


def redirected_request(
    initial: str, destination: str, proxies: dict[str, str]
) -> tuple[requests.PreparedRequest, dict[str, Any]]:
    adapter = RecordingTransport(destination)
    with requests.Session() as session:
        session.trust_env = False
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        response = session.get(
            initial, proxies=proxies, headers={"X-Control": "preserved"}
        )
    assert response.status_code == 200
    assert len(adapter.sent) == 2
    return adapter.sent[1]


def test_security_regression() -> None:
    for initial in ("http://source.example/start", "https://source.example/start"):
        request, options = redirected_request(
            initial,
            "https://destination.example/result",
            {"http": PROXY, "https": PROXY},
        )
        assert "Proxy-Authorization" not in request.headers, (
            "EXPECTED_SECURITY_REGRESSION: proxy credentials reached HTTPS destination"
        )
        assert options["proxies"]["https"] == PROXY


def test_http_proxy_auth_retained() -> None:
    request, options = redirected_request(
        "https://source.example/start",
        "http://destination.example/result",
        {"http": PROXY},
    )
    assert request.headers["Proxy-Authorization"] == BASIC_AUTH
    assert options["proxies"]["http"] == PROXY


def test_https_tunnel_auth_retained() -> None:
    assert HTTPAdapter().proxy_headers(PROXY) == {"Proxy-Authorization": BASIC_AUTH}


def test_ordinary_redirect_metadata_retained() -> None:
    request, _options = redirected_request(
        "http://source.example/start", "https://destination.example/result", {}
    )
    assert request.method == "GET"
    assert request.url == "https://destination.example/result"
    assert request.headers["X-Control"] == "preserved"
    assert "Proxy-Authorization" not in request.headers
