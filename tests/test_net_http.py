"""Tests for orphee.net.http — offline: session.get mocked, cache in tmp_path."""

import gzip
import json

import pytest
import requests

from orphee.net import http
from orphee.net.http import FetchError, HttpClient, cache_key


def _response(
    body: bytes, status: int = 200, headers: dict[str, str] | None = None
) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp._content = body
    resp.headers.update(headers or {})
    resp.url = "https://example.test/page"
    return resp


@pytest.fixture
def client(tmp_path, monkeypatch) -> HttpClient:
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    return HttpClient(cache_dir=tmp_path / "cache", min_interval_s=0.0)


def test_cache_miss_then_hit(client: HttpClient, monkeypatch) -> None:
    calls: list[str] = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return _response(b"<html>hello</html>")

    monkeypatch.setattr(client.session, "get", fake_get)
    url = "https://example.test/a"
    assert client.get(url) == b"<html>hello</html>"
    assert client.get(url) == b"<html>hello</html>"
    assert calls == [url]  # second call served from the disk cache
    assert client.has(url)
    meta = json.loads(client.meta_path(url).read_text(encoding="utf-8"))
    assert meta["status"] == 200
    assert meta["bytes"] == len(b"<html>hello</html>")
    assert gzip.decompress(client.cache_path(url).read_bytes()) == b"<html>hello</html>"


def test_params_change_cache_key() -> None:
    url = "https://x.test/a"
    assert cache_key(url, {"p": 1}) != cache_key(url)
    assert cache_key(url, {"p": 1}) == cache_key(url, {"p": 1})


def test_retry_on_503_then_success(client: HttpClient, monkeypatch) -> None:
    responses = [_response(b"", status=503), _response(b"ok")]
    state = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        resp = responses[min(state["n"], len(responses) - 1)]
        state["n"] += 1
        return resp

    monkeypatch.setattr(client.session, "get", fake_get)
    assert client.get("https://example.test/b") == b"ok"
    assert state["n"] == 2


def test_404_fails_without_retry(client: HttpClient, monkeypatch) -> None:
    calls: list[str] = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return _response(b"nope", status=404)

    monkeypatch.setattr(client.session, "get", fake_get)
    with pytest.raises(FetchError):
        client.get("https://example.test/missing")
    assert calls == ["https://example.test/missing"]


def test_429_above_cap_fails_fast(client: HttpClient, monkeypatch) -> None:
    calls: list[str] = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return _response(b"", status=429, headers={"Retry-After": "3600"})

    monkeypatch.setattr(client.session, "get", fake_get)
    with pytest.raises(FetchError, match="Retry-After"):
        client.get("https://example.test/slow")
    assert len(calls) == 1  # no retry: the announced wait is above the cap


def test_429_within_cap_is_retried(client: HttpClient, monkeypatch) -> None:
    responses = [
        _response(b"", status=429, headers={"Retry-After": "1"}),
        _response(b"ok"),
    ]
    state = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        resp = responses[min(state["n"], len(responses) - 1)]
        state["n"] += 1
        return resp

    monkeypatch.setattr(client.session, "get", fake_get)
    assert client.get("https://example.test/c") == b"ok"
    assert state["n"] == 2


def test_transient_network_error_is_retried_then_succeeds(
    client: HttpClient, monkeypatch
) -> None:
    # e.g. ChunkedEncodingError "Response ended prematurely" mid-PDF (seen live)
    state = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        state["n"] += 1
        if state["n"] == 1:
            raise requests.exceptions.ChunkedEncodingError("Response ended prematurely")
        return _response(b"ok")

    monkeypatch.setattr(client.session, "get", fake_get)
    assert client.get("https://example.test/d") == b"ok"
    assert state["n"] == 2


def test_persistent_network_error_becomes_fetch_error(
    client: HttpClient, monkeypatch
) -> None:
    calls: list[str] = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        raise requests.exceptions.ConnectionError("connection reset")

    monkeypatch.setattr(client.session, "get", fake_get)
    with pytest.raises(FetchError, match="network error"):
        client.get("https://example.test/e")
    assert len(calls) == 4  # retried, then surfaced as a permanent FetchError
