"""Tests for orphee.crawl — offline: a fake client serves synthetic sitemaps."""

import json
from typing import Any

from orphee import crawl
from orphee.net.http import FetchError
from orphee.sources import SourceSpec


class FakeClient:
    """Same surface as HttpClient, serving canned bytes; no disk cache."""

    def __init__(self, responses: dict[str, bytes]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def has(self, url: str, params: dict[str, Any] | None = None) -> bool:
        return False

    def get(self, url: str, params: dict[str, Any] | None = None) -> bytes:
        self.calls.append(url)
        if url not in self.responses:
            raise FetchError(f"HTTP 404: {url}")
        return self.responses[url]

    def get_text(
        self, url: str, params: dict[str, Any] | None = None, encoding: str = "utf-8"
    ) -> str:
        return self.get(url, params).decode(encoding)


SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://asnr.test/sitemap-notices-1.xml</loc></sitemap>
  <sitemap><loc>https://asnr.test/sitemap-other-1.xml</loc></sitemap>
</sitemapindex>
"""

NOTICES_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://asnr.test/avis/avis-a</loc></url>
  <url><loc>https://asnr.test/avis/avis-b</loc></url>
  <url><loc>https://asnr.test/avis/avis-a</loc></url>
</urlset>
"""

OTHER_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://asnr.test/avis</loc></url>
  <url><loc>https://asnr.test/autre-page</loc></url>
  <url><loc>https://asnr.test/avis/avis-c?page=2</loc></url>
</urlset>
"""

SPEC = SourceSpec(
    name="incident_notices",
    base="https://asnr.test",
    listing_path="/avis",
    notice_path_prefix="/avis/",
    rss_path="/rss/avis",
    default_crawl_delay_s=10.0,
)


def _client() -> FakeClient:
    return FakeClient(
        {
            "https://asnr.test/sitemap.xml": SITEMAP_INDEX.encode(),
            "https://asnr.test/sitemap-notices-1.xml": NOTICES_SITEMAP.encode(),
            "https://asnr.test/sitemap-other-1.xml": OTHER_SITEMAP.encode(),
            "https://asnr.test/avis/avis-a": b"<html>a</html>",
            "https://asnr.test/avis/avis-b": b"<html>b</html>",
            # avis-c intentionally missing -> FetchError
        }
    )


def test_enumerate_urls_filters_and_dedupes() -> None:
    urls = crawl.enumerate_urls(_client(), SPEC)
    assert urls == ["https://asnr.test/avis/avis-a", "https://asnr.test/avis/avis-b"]


def test_fetch_urls_writes_manifest_and_survives_errors(tmp_path) -> None:
    client = _client()
    urls = [
        "https://asnr.test/avis/avis-a",
        "https://asnr.test/avis/avis-b",
        "https://asnr.test/avis/avis-c",
    ]
    summary = crawl.fetch_urls(client, tmp_path, urls)
    assert summary.enumerated == 3
    assert summary.fetched == 2
    assert summary.errors == 1
    manifest = (tmp_path / "manifest.jsonl").read_text(encoding="utf-8")
    lines = [json.loads(line) for line in manifest.splitlines()]
    assert [line["status"] for line in lines] == ["ok", "ok", "error"]
    assert lines[0]["bytes"] == len(b"<html>a</html>")


def test_fetch_urls_respects_limit(tmp_path) -> None:
    urls = crawl.enumerate_urls(_client(), SPEC) + ["https://asnr.test/avis/avis-c"]
    summary = crawl.fetch_urls(_client(), tmp_path, urls, limit=1)
    assert summary.fetched == 1
    assert len((tmp_path / "manifest.jsonl").read_text().splitlines()) == 1


def test_crawl_source_writes_urls_txt(tmp_path) -> None:
    summary = crawl.crawl_source(_client(), SPEC, tmp_path)
    assert summary.enumerated == 2
    assert summary.fetched == 2
    assert (tmp_path / "urls.txt").read_text(encoding="utf-8").splitlines() == [
        "https://asnr.test/avis/avis-a",
        "https://asnr.test/avis/avis-b",
    ]


# --- paginated-listing mode (documents not in the sitemap, e.g. PDFs) ------

LETTER_SPEC = SourceSpec(
    name="inspection_letters_inb",
    base="https://asnr.test",
    listing_path="/lettres",
    notice_path_prefix="/content/download/",
    rss_path="/rss/lettres",
    default_crawl_delay_s=10.0,
    doc_url_regex=r"/content/download/\d+/download_file/INSSN-[A-Z]+-\d{4}-\d+\.pdf$",
)

LETTER_A = (
    "https://asnr.test/content/download/101/download_file/INSSN-CAE-2025-0257.pdf"
)
LETTER_B = (
    "https://asnr.test/content/download/102/download_file/INSSN-OLS-2026-0866.pdf"
)
LETTER_C = (
    "https://asnr.test/content/download/104/download_file/INSSN-LYO-2026-0643.pdf"
)

LISTING_ROOT = f"""<html><body>
<a href="{LETTER_A}">lettre A</a>
<a href="/lettres/autre-chose">not a document</a>
</body></html>"""
LISTING_PAGE_1 = f"""<html><body>
<a href="{LETTER_B}">lettre B</a>
<a href="/content/download/103/download_file/autre.pdf">wrong name</a>
</body></html>"""
LISTING_PAGE_2 = f"""<html><body><a href="{LETTER_C}">lettre C</a></body></html>"""
LISTING_PAGE_3 = """<html><body><a href="/lettres">rien ici</a></body></html>"""


def _listing_client() -> FakeClient:
    # root page first (page 1), then ?page=N; unknown urls -> FetchError (404)
    return FakeClient(
        {
            "https://asnr.test/lettres": LISTING_ROOT.encode(),
            "https://asnr.test/lettres?page=1": LISTING_PAGE_1.encode(),
            "https://asnr.test/lettres?page=2": LISTING_PAGE_2.encode(),
            "https://asnr.test/lettres?page=3": LISTING_PAGE_3.encode(),
        }
    )


def test_enumerate_listing_urls_matches_regex_and_stops() -> None:
    client = _listing_client()
    urls = crawl.enumerate_urls(client, LETTER_SPEC)
    assert urls == [LETTER_A, LETTER_B, LETTER_C]
    # page 3 has no matching link -> enumeration stops before page 4
    assert "https://asnr.test/lettres?page=4" not in client.calls


def test_enumerate_listing_urls_tolerates_transient_errors() -> None:
    client = _listing_client()
    # ?page=1 fails (404): enumeration must continue to ?page=2, ?page=3
    del client.responses["https://asnr.test/lettres?page=1"]
    urls = crawl.enumerate_urls(client, LETTER_SPEC)
    assert urls == [LETTER_A, LETTER_C]


def test_enumerate_listing_urls_respects_max_pages() -> None:
    client = _listing_client()
    urls = crawl.enumerate_urls(client, LETTER_SPEC, max_listing_pages=1)
    assert urls == [LETTER_A, LETTER_B]
    assert "https://asnr.test/lettres?page=2" not in client.calls
