"""Tests for orphee.data.ingest — offline, synthetic cache sidecars + bodies."""

import gzip
import json
from pathlib import Path

from orphee.data.ingest import ingest_cache
from orphee.data.models import IncidentNotice, InspectionLetter
from orphee.net.http import cache_key

PREFIX = "https://asnr.test/avis/"
URL_A = PREFIX + "avis-a"
URL_B = PREFIX + "avis-b"
URL_BAD = PREFIX + "avis-bad"
URL_OTHER = "https://asnr.test/sitemap.xml"  # outside the prefix: ignored


def _write_cache(raw_dir: Path, url: str, html: str) -> str:
    """Write a cache entry exactly like HttpClient.get does: .gz + .json."""
    key = cache_key(url)
    cache = raw_dir / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / f"{key}.gz").write_bytes(gzip.compress(html.encode("utf-8")))
    (cache / f"{key}.json").write_text(
        json.dumps({"url": url, "status": 200, "bytes": len(html)}), encoding="utf-8"
    )
    return key


def test_ingest_cache(tmp_path: Path, synthetic_notice_html: str) -> None:
    raw_dir = tmp_path / "raw"
    _write_cache(raw_dir, URL_A, synthetic_notice_html)
    _write_cache(raw_dir, URL_B, synthetic_notice_html)
    _write_cache(raw_dir, URL_BAD, "<html></html>")  # unparseable -> error
    _write_cache(raw_dir, URL_OTHER, "<xml/>")  # outside prefix -> ignored
    # torn sidecar (mid-write): skipped, not fatal
    torn = raw_dir / "cache" / "deadbeef.json"
    torn.write_text('{"url": "https://asnr.t', encoding="utf-8")

    out = tmp_path / "out" / "notices.jsonl"
    report = ingest_cache(raw_dir, out, url_prefix=PREFIX)
    assert report.total == 3  # A, B, BAD — the sitemap entry is filtered out
    assert report.parsed == 2
    assert report.skipped == 1
    assert len(report.errors) == 1 and URL_BAD in report.errors[0]
    assert report.ines_counts[2] == 2
    assert report.missing["updated"] == 0
    assert report.published_min is not None
    assert report.published_min.isoformat() == "2017-02-15"

    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    notices = [IncidentNotice.model_validate_json(line) for line in lines]
    assert {n.id for n in notices} == {"avis-a", "avis-b"}
    assert all(n.max_freshness.isoformat() == "2021-09-03" for n in notices)


def test_ingest_cache_limit(tmp_path: Path, synthetic_notice_html: str) -> None:
    raw_dir = tmp_path / "raw"
    _write_cache(raw_dir, URL_A, synthetic_notice_html)
    _write_cache(raw_dir, URL_B, synthetic_notice_html)
    report = ingest_cache(raw_dir, tmp_path / "out.jsonl", limit=1, url_prefix=PREFIX)
    assert report.total == 1
    assert report.parsed == 1


LETTER_URL = (
    "https://asnr.test/content/download/203064/download_file/INSSN-CAE-2025-0257.pdf"
)


def test_ingest_pdf_source(tmp_path: Path, synthetic_letter_pdf: bytes) -> None:
    raw_dir = tmp_path / "raw"
    key = cache_key(LETTER_URL)
    cache = raw_dir / "cache"
    cache.mkdir(parents=True)
    (cache / f"{key}.gz").write_bytes(gzip.compress(synthetic_letter_pdf))
    (cache / f"{key}.json").write_text(
        json.dumps(
            {
                "url": LETTER_URL,
                "status": 200,
                "content_type": "application/pdf",
                "bytes": len(synthetic_letter_pdf),
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "letters.jsonl"
    report = ingest_cache(
        raw_dir,
        out,
        url_prefix="https://asnr.test/content/download/",
        source="inspection_letters_inb",
    )
    assert report.total == 1
    assert report.parsed == 1
    assert report.published_min is not None
    assert report.published_min.isoformat() == "2025-02-27"
    line = out.read_text(encoding="utf-8").splitlines()[0]
    letter = InspectionLetter.model_validate_json(line)
    assert letter.reference == "INSSN-CAE-2025-0257"
    assert letter.division == "CAE"
    assert letter.pdf_pages == 1
    assert letter.theme == "la surveillance des activites"


def test_ingest_pdf_source_counts_errors(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    key = cache_key(LETTER_URL)
    cache = raw_dir / "cache"
    cache.mkdir(parents=True)
    (cache / f"{key}.gz").write_bytes(gzip.compress(b"not a pdf at all"))
    meta = {"url": LETTER_URL, "status": 200, "content_type": "application/pdf"}
    (cache / f"{key}.json").write_text(json.dumps(meta), encoding="utf-8")
    report = ingest_cache(
        raw_dir,
        tmp_path / "out.jsonl",
        url_prefix="https://asnr.test/content/download/",
        source="inspection_letters_inb",
    )
    assert report.parsed == 0
    assert len(report.errors) == 1 and LETTER_URL in report.errors[0]
