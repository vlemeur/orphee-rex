"""Tests for orphee.data.ingest — offline, synthetic cache + manifest."""

import gzip
import json
from pathlib import Path

from orphee.data.ingest import ingest_cache
from orphee.data.models import IncidentNotice
from orphee.net.http import cache_key

URL_A = "https://asnr.test/avis/avis-a"
URL_B = "https://asnr.test/avis/avis-b"
URL_BAD = "https://asnr.test/avis/avis-bad"


def _write_cache(raw_dir: Path, url: str, html: str) -> str:
    key = cache_key(url)
    cache = raw_dir / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / f"{key}.gz").write_bytes(gzip.compress(html.encode("utf-8")))
    return key


def _write_manifest(raw_dir: Path, entries: list[dict]) -> None:
    (raw_dir / "manifest.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n",
        encoding="utf-8",
    )


def test_ingest_cache(tmp_path: Path, synthetic_notice_html: str) -> None:
    raw_dir = tmp_path / "raw"
    entries = [
        {
            "url": URL_A,
            "key": _write_cache(raw_dir, URL_A, synthetic_notice_html),
            "status": "ok",
        },
        {
            "url": URL_B,
            "key": _write_cache(raw_dir, URL_B, synthetic_notice_html),
            "status": "ok",
        },
        {
            "url": URL_BAD,
            "key": _write_cache(raw_dir, URL_BAD, "<html></html>"),
            "status": "ok",
        },
        {
            "url": "https://asnr.test/avis/avis-err",
            "key": "deadbeef",
            "status": "error",
        },
    ]
    _write_manifest(raw_dir, entries)

    out = tmp_path / "out" / "notices.jsonl"
    report = ingest_cache(raw_dir, out)
    assert report.total == 3  # the "error" manifest line is skipped
    assert report.parsed == 2
    assert len(report.errors) == 1 and URL_BAD in report.errors[0]
    assert report.ines_counts[2] == 2
    assert report.missing["updated"] == 0
    assert report.published_min is not None
    assert report.published_min.isoformat() == "2017-02-15"

    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    notice = IncidentNotice.model_validate_json(lines[0])
    assert notice.id == "avis-a"
    assert notice.max_freshness.isoformat() == "2021-09-03"


def test_ingest_cache_limit(tmp_path: Path, synthetic_notice_html: str) -> None:
    raw_dir = tmp_path / "raw"
    entry = {
        "url": URL_A,
        "key": _write_cache(raw_dir, URL_A, synthetic_notice_html),
        "status": "ok",
    }
    _write_manifest(raw_dir, [entry])
    report = ingest_cache(raw_dir, tmp_path / "out.jsonl", limit=0)
    assert report.total == 0
    assert report.parsed == 0
