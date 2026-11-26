"""Ingest the raw HTML cache into parsed JSONL — offline (reads data/ only).

Source of truth = the HttpClient disk cache under raw_dir/cache/: each
<sha256>.json sidecar carries the url, each <sha256>.gz the body (both
written and closed per page, so a mid-scrape ingest sees every fetched
page). The scrape manifest stays an append-only audit log. Pages are
filtered on url_prefix, parsed with parse.parse_notice, and written one
JSON record per line. Unparseable pages / unreadable sidecars are counted
in the report, never fatal.
"""

from __future__ import annotations

import gzip
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from orphee.data.parse import ParseError, parse_notice

OPTIONAL_FIELDS = ("updated", "site", "site_detail", "ines_level", "chapo")


@dataclass
class IngestReport:
    total: int = 0  # manifest lines with status ok/cache_hit
    parsed: int = 0
    skipped: int = 0  # malformed manifest lines (torn trailing line mid-scrape)
    errors: list[str] = field(default_factory=list)
    missing: Counter[str] = field(default_factory=Counter)
    ines_counts: Counter[int] = field(default_factory=Counter)
    published_min: date | None = None
    published_max: date | None = None
    body_chars: int = 0


def ingest_cache(
    raw_dir: Path | str,
    out_path: Path | str,
    limit: int | None = None,
    url_prefix: str | None = None,
) -> IngestReport:
    """Parse the cached pages of raw_dir/cache into out_path (JSONL).

    Cache sidecars (<sha256>.json, each with its url) drive the enumeration,
    so a mid-scrape run sees every page already fetched. url_prefix filters
    documents (e.g. the incident-notice path); limit caps how many are read.
    """
    raw_dir = Path(raw_dir)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = IngestReport()
    cache_dir = raw_dir / "cache"
    entries: list[tuple[str, str]] = []  # (url, key)
    if cache_dir.exists():
        for meta_path in sorted(cache_dir.glob("*.json")):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError, OSError:
                report.skipped += 1  # torn sidecar mid-write
                continue
            url = str(meta.get("url", ""))
            if url_prefix is not None and not url.startswith(url_prefix):
                continue
            entries.append((url, meta_path.stem))
    if limit is not None:
        entries = entries[:limit]
    with out_path.open("w", encoding="utf-8") as out:
        for url, key in entries:
            report.total += 1
            gz = cache_dir / f"{key}.gz"
            try:
                html = gzip.decompress(gz.read_bytes()).decode("utf-8", "replace")
                notice = parse_notice(html, url)
            except (ParseError, OSError) as exc:
                report.errors.append(f"{url}: {exc}")
                continue
            out.write(notice.model_dump_json() + "\n")
            report.parsed += 1
            for name in OPTIONAL_FIELDS:
                if getattr(notice, name) is None:
                    report.missing[name] += 1
            if notice.ines_level is not None:
                report.ines_counts[notice.ines_level] += 1
            report.body_chars += len(notice.body)
            if report.published_min is None or notice.published < report.published_min:
                report.published_min = notice.published
            if report.published_max is None or notice.published > report.published_max:
                report.published_max = notice.published
    return report
