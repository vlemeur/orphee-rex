"""Crawl one source's documents into the raw on-disk cache + a manifest.

Enumeration has two modes (see sources.SourceSpec):
- sitemap: ``/sitemap.xml`` (index or urlset) -> child sitemaps -> URLs
  filtered on the source's document path prefix (HTML articles);
- paginated listing: when the spec sets ``doc_url_regex``, the documents are
  not in the sitemap (e.g. PDF downloads) — the listing pages ``?page=0..N``
  are crawled and every link matching the regex is kept.
Fetching goes through ``net.http.HttpClient``, whose disk cache is the raw
store, so re-runs are free and resumable. Layout under raw_dir:
  urls.txt         enumerated document URLs (one per line)
  manifest.jsonl   one line per document: url, key, status, bytes, fetched_at
  cache/           the HttpClient cache (<sha256>.gz bodies + .json sidecars)
A broken page is a manifest line with status="error", never a crash.
"""

from __future__ import annotations

import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from tqdm import tqdm

from orphee.net.http import FetchClient, FetchError, cache_key
from orphee.sources import SourceSpec

logger = logging.getLogger(__name__)

DEFAULT_MAX_SITEMAPS = 500


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _sitemap_locs(xml_text: str) -> tuple[list[str], list[str]]:
    """Return (document urls, child sitemap urls) of a sitemap index or urlset."""
    root = ET.fromstring(xml_text)
    locs = [e.text for e in root.iter() if _localname(e.tag) == "loc" and e.text]
    if _localname(root.tag) == "sitemapindex":
        return [], locs
    return locs, []


def enumerate_listing_urls(
    client: FetchClient,
    spec: SourceSpec,
    max_pages: int | None = None,
) -> list[str]:
    """Document URLs found by crawling the source's paginated listing pages.

    Used when the spec sets ``doc_url_regex`` (documents not listed in the
    sitemap, e.g. PDF downloads): pages ``<listing>?page=0..N`` are fetched
    until one yields no new matching link, or ``max_pages`` is reached.
    """
    if spec.doc_url_regex is None:
        raise ValueError(f"{spec.name}: doc_url_regex not set (sitemap source?)")
    pattern = re.compile(spec.doc_url_regex)
    listing = spec.base + spec.listing_path
    max_pages = max_pages if max_pages is not None else spec.listing_max_pages
    # The root listing page is page 1; ?page=0 may not exist (404) — so crawl
    # the root page first, then ?page=1..N, tolerating a few consecutive fetch
    # errors (transient) and stopping on the first page without any match.
    page_urls = [listing] + [f"{listing}?page={p}" for p in range(1, max_pages + 1)]
    docs: set[str] = set()
    consecutive_errors = 0
    for url in tqdm(page_urls, desc="listing pages", unit="page"):
        try:
            html = client.get_text(url)
        except FetchError as exc:
            consecutive_errors += 1
            logger.warning("listing page failed: %s (%s)", url, exc)
            if consecutive_errors >= 3:
                break
            continue
        consecutive_errors = 0
        soup = BeautifulSoup(html, "html.parser")
        found = {
            urljoin(url, str(a["href"]))
            for a in soup.find_all("a", href=True)
            if pattern.search(urljoin(url, str(a["href"])))
        }
        if not found:
            break
        docs.update(found)
    result = sorted(docs)
    logger.info("%s: %d document urls from paginated listing", spec.name, len(result))
    return result


def enumerate_urls(
    client: FetchClient,
    spec: SourceSpec,
    max_sitemaps: int = DEFAULT_MAX_SITEMAPS,
    max_listing_pages: int | None = None,
) -> list[str]:
    """All document URLs of the source (sitemap mode or paginated-listing mode)."""
    if spec.doc_url_regex is not None:
        return enumerate_listing_urls(client, spec, max_pages=max_listing_pages)
    urls, children = _sitemap_locs(client.get_text(f"{spec.base}/sitemap.xml"))
    for child in tqdm(children[:max_sitemaps], desc="sitemaps", unit="sitemap"):
        child_urls, _ = _sitemap_locs(client.get_text(child))
        urls.extend(child_urls)
    listing = spec.base + spec.listing_path
    doc_prefix = spec.base + spec.notice_path_prefix
    docs = sorted(
        {u for u in urls if u.startswith(doc_prefix) and u != listing and "?" not in u}
    )
    logger.info(
        "%s: %d document urls from %d sitemap entries", spec.name, len(docs), len(urls)
    )
    return docs


@dataclass
class CrawlSummary:
    enumerated: int
    fetched: int
    cache_hits: int
    errors: int
    elapsed_s: float


def fetch_urls(
    client: FetchClient,
    raw_dir: Path | str,
    urls: list[str],
    limit: int | None = None,
) -> CrawlSummary:
    """Fetch document URLs into the client cache; append one manifest line each."""
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = raw_dir / "manifest.jsonl"
    todo = urls[:limit] if limit is not None else urls
    fetched = cache_hits = errors = 0
    start = time.monotonic()
    with manifest_path.open("a", encoding="utf-8") as manifest:
        for url in tqdm(todo, desc="scrape", unit="page"):
            record = {
                "url": url,
                "key": cache_key(url),
                "fetched_at": datetime.now(UTC).isoformat(),
            }
            if client.has(url):
                record.update(status="cache_hit", bytes=None)
                cache_hits += 1
            else:
                try:
                    body = client.get(url)
                    record.update(status="ok", bytes=len(body))
                    fetched += 1
                except Exception as exc:
                    # a broken page is a manifest error line, never a crash
                    record.update(status="error", error=f"{type(exc).__name__}: {exc}")
                    errors += 1
                    logger.warning("fetch failed: %s (%s)", url, exc)
            manifest.write(json.dumps(record, ensure_ascii=False) + "\n")
    return CrawlSummary(
        enumerated=len(urls),
        fetched=fetched,
        cache_hits=cache_hits,
        errors=errors,
        elapsed_s=time.monotonic() - start,
    )


def crawl_source(
    client: FetchClient,
    spec: SourceSpec,
    raw_dir: Path | str,
    limit: int | None = None,
    max_sitemaps: int = DEFAULT_MAX_SITEMAPS,
    max_listing_pages: int | None = None,
) -> CrawlSummary:
    """Enumerate the source's documents, save urls.txt, then fetch them."""
    raw_dir = Path(raw_dir)
    urls = enumerate_urls(
        client, spec, max_sitemaps=max_sitemaps, max_listing_pages=max_listing_pages
    )
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "urls.txt").write_text("\n".join(urls) + "\n", encoding="utf-8")
    return fetch_urls(client, raw_dir, urls, limit=limit)
