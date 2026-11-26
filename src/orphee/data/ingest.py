"""Ingest the raw HTML cache into parsed JSONL — offline (reads data/ only).

Reads the manifest + gzipped cache written by `just scrape`, parses each
page with parse.parse_notice, and writes one JSON record per notice.
Unparseable pages are counted in the report, never fatal.
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
    errors: list[str] = field(default_factory=list)
    missing: Counter[str] = field(default_factory=Counter)
    ines_counts: Counter[int] = field(default_factory=Counter)
    published_min: date | None = None
    published_max: date | None = None
    body_chars: int = 0


def ingest_cache(
    raw_dir: Path | str, out_path: Path | str, limit: int | None = None
) -> IngestReport:
    """Parse every cached page listed in raw_dir/manifest.jsonl into out_path."""
    raw_dir = Path(raw_dir)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = IngestReport()
    lines = (raw_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    if limit is not None:
        lines = lines[:limit]
    with out_path.open("w", encoding="utf-8") as out:
        for line in lines:
            entry = json.loads(line)
            if entry.get("status") not in ("ok", "cache_hit"):
                continue
            report.total += 1
            url, key = entry["url"], entry["key"]
            gz = raw_dir / "cache" / f"{key}.gz"
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
