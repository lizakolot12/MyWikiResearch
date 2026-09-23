"""http_get_json (standard-library client) against a local HTTP server."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from wikitrend import api


class Handler(BaseHTTPRequestHandler):
    fails_left = 0
    seen = []

    def do_GET(self):  # noqa: N802
        Handler.seen.append((self.path, self.headers.get("User-Agent")))
        path = urlparse(self.path)
        if path.path == "/missing":
            self.send_error(404)
        elif path.path == "/flaky" and Handler.fails_left:
            Handler.fails_left -= 1
            self.send_error(503)
        elif path.path == "/bad":
            self.send_error(400, "bad request")
        else:
            body = json.dumps({"query": parse_qs(path.query), "text": "Астрономія"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(api.time, "sleep", lambda s: None)  # no real backoff in tests
    Handler.seen = []
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_json_params_and_user_agent(server):
    data = api.http_get_json(f"{server}/ok", {"action": "query", "titles": "Астрономія"})
    assert data["text"] == "Астрономія"
    assert data["query"] == {"action": ["query"], "titles": ["Астрономія"]}
    assert Handler.seen[0][1] == api.USER_AGENT


def test_404_means_no_data(server):
    assert api.http_get_json(f"{server}/missing") is None


def test_retries_server_errors(server):
    Handler.fails_left = 2
    assert api.http_get_json(f"{server}/flaky")["text"] == "Астрономія"
    assert len(Handler.seen) == 3


def test_client_error_is_not_retried(server):
    with pytest.raises(api.ApiError, match="HTTP 400"):
        api.http_get_json(f"{server}/bad")
    assert len(Handler.seen) == 1


def test_network_error(monkeypatch):
    monkeypatch.setattr(api.time, "sleep", lambda s: None)
    with pytest.raises(api.ApiError, match="network error"):
        api.http_get_json("http://127.0.0.1:1/unreachable")
