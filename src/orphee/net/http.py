"""HTTP client with politeness, retries and a URL-keyed disk cache.

The cache is the raw store: each response body is written gzipped as
``<sha256>.gz`` next to a ``<sha256>.json`` sidecar (url, status, fetched_at,
content_type, bytes). A cache hit never touches the network, so re-runs are
free and resumable. Tests monkeypatch ``client.session.get`` and
``orphee.net.http.time.sleep`` — no network in tests.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

USER_AGENT = "orphee-rex/0.1 (+https://github.com/vlemeur/orphee-rex)"
DEFAULT_TIMEOUT_S = 60.0
# A 429 whose Retry-After announces a wait above this cap fails fast instead
# of sleeping: a CI job must never block for hours on a shared-IP quota.
DEFAULT_MAX_429_WAIT_S = 60.0
RETRYABLE_STATUS = {500, 502, 503, 504}


class FetchClient(Protocol):
    """The mockable fetch surface: everything crawl.py needs from a client."""

    def has(self, url: str, params: dict[str, Any] | None = None) -> bool: ...

    def get(self, url: str, params: dict[str, Any] | None = None) -> bytes: ...

    def get_text(
        self, url: str, params: dict[str, Any] | None = None, encoding: str = "utf-8"
    ) -> str: ...


class FetchError(Exception):
    """Permanent fetch failure (4xx, or 429 above the wait cap)."""


class RetryableFetchError(Exception):
    """Transient fetch failure (429, 5xx) — retried with backoff."""


def cache_key(url: str, params: dict[str, Any] | None = None) -> str:
    """Stable key for a GET request: sha256 of the prepared URL."""
    if params:
        params = dict(sorted(params.items()))
    prepared = requests.Request("GET", url, params=params).prepare()
    return hashlib.sha256(prepared.url.encode("utf-8")).hexdigest()


def _retry_after_s(resp: requests.Response) -> float | None:
    """Numeric Retry-After header, if any (the HTTP-date form is ignored)."""
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


class HttpClient:
    """The single network gateway: polite, retrying, caching GETs."""

    def __init__(
        self,
        cache_dir: Path | str = "data/cache/http",
        min_interval_s: float = 1.0,
        user_agent: str = USER_AGENT,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_429_wait_s: float = DEFAULT_MAX_429_WAIT_S,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval_s = min_interval_s
        self.timeout_s = timeout_s
        self.max_429_wait_s = max_429_wait_s
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self._last_request_at = 0.0

    # -- cache ------------------------------------------------------------

    def cache_path(self, url: str, params: dict[str, Any] | None = None) -> Path:
        return self.cache_dir / f"{cache_key(url, params)}.gz"

    def meta_path(self, url: str, params: dict[str, Any] | None = None) -> Path:
        return self.cache_dir / f"{cache_key(url, params)}.json"

    def has(self, url: str, params: dict[str, Any] | None = None) -> bool:
        """True if the response is already in the disk cache."""
        return self.cache_path(url, params).exists()

    # -- public API ---------------------------------------------------------

    def get(self, url: str, params: dict[str, Any] | None = None) -> bytes:
        """GET url (with optional query params), from cache when available."""
        if self.has(url, params):
            logger.debug("cache hit: %s", url)
            return gzip.decompress(self.cache_path(url, params).read_bytes())
        resp = self._fetch(url, params)
        body = resp.content
        self.cache_path(url, params).write_bytes(gzip.compress(body))
        meta = {
            "url": resp.url,
            "status": resp.status_code,
            "content_type": resp.headers.get("Content-Type"),
            "fetched_at": datetime.now(UTC).isoformat(),
            "bytes": len(body),
        }
        self.meta_path(url, params).write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )
        return body

    def get_text(
        self, url: str, params: dict[str, Any] | None = None, encoding: str = "utf-8"
    ) -> str:
        return self.get(url, params).decode(encoding, errors="replace")

    # -- internals ----------------------------------------------------------

    def _throttle(self) -> None:
        if self.min_interval_s <= 0:
            return
        wait = self.min_interval_s - (time.monotonic() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def _fetch(self, url: str, params: dict[str, Any] | None) -> requests.Response:
        try:
            return self._fetch_with_retries(url, params)
        except RetryableFetchError as exc:
            raise FetchError(str(exc)) from exc

    @retry(
        retry=retry_if_exception_type(RetryableFetchError),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        reraise=True,
    )
    def _fetch_with_retries(
        self, url: str, params: dict[str, Any] | None
    ) -> requests.Response:
        self._throttle()
        logger.info("fetching: %s", url)
        resp = self.session.get(url, params=params, timeout=self.timeout_s)
        if resp.status_code == 429:
            wait_s = _retry_after_s(resp)
            if wait_s is not None and wait_s > self.max_429_wait_s:
                raise FetchError(
                    f"429 Retry-After={wait_s}s > cap {self.max_429_wait_s}s: {url}"
                )
            if wait_s is not None:
                time.sleep(min(wait_s, self.max_429_wait_s))
            raise RetryableFetchError(f"429: {url}")
        if resp.status_code in RETRYABLE_STATUS:
            raise RetryableFetchError(f"HTTP {resp.status_code}: {url}")
        if resp.status_code >= 400:
            raise FetchError(f"HTTP {resp.status_code}: {url}")
        return resp
