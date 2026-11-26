"""Ingest the raw ASNR HTML cache into parsed JSONL (offline).

Thin CLI over src/orphee/data/ingest.py: reads the cache under
data/raw/asnr/<source>/cache (written page-per-page by `just scrape`) and
writes one JSON record per notice to data/interim/. Safe to run mid-scrape.
Examples:
    uv run python scripts/ingest.py --limit 200
    uv run python scripts/ingest.py
"""

from __future__ import annotations

import argparse
import logging

from orphee import sources
from orphee.data.ingest import ingest_cache


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", choices=sorted(sources.SOURCES), default="incident_notices"
    )
    parser.add_argument(
        "--raw-dir", default=None, help="default data/raw/asnr/<source>"
    )
    parser.add_argument(
        "--out", default=None, help="default data/interim/<source>.jsonl"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="max cached pages to read"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    spec = sources.SOURCES[args.source]
    raw_dir = args.raw_dir or f"data/raw/asnr/{spec.name}"
    out = args.out or f"data/interim/{spec.name}.jsonl"
    url_prefix = spec.base + spec.notice_path_prefix
    report = ingest_cache(raw_dir, out, limit=args.limit, url_prefix=url_prefix)
    print(f"\ningest: {report.parsed}/{report.total} notices parsed -> {out}")
    if report.skipped:
        print(f"skipped {report.skipped} unreadable cache sidecar(s) (mid-scrape?)")
    print(
        f"published: {report.published_min} .. {report.published_max}, "
        f"body chars total: {report.body_chars}"
    )
    print(f"INES levels: {dict(sorted(report.ines_counts.items()))}")
    print(f"missing fields: {dict(report.missing)}")
    for err in report.errors[:10]:
        print(f"  error: {err}")
    if len(report.errors) > 10:
        print(f"  ... and {len(report.errors) - 10} more")


if __name__ == "__main__":
    main()
