"""Ingest the raw ASNR HTML cache into parsed JSONL (offline).

Thin CLI over src/orphee/data/ingest.py: reads data/raw/asnr/<source>
(manifest + cache written by `just scrape`) and writes one JSON record per
notice to data/interim/. Examples:
    uv run python scripts/ingest.py --limit 50
    uv run python scripts/ingest.py
"""

from __future__ import annotations

import argparse
import logging

from orphee.data.ingest import ingest_cache


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", default="data/raw/asnr/incident_notices")
    parser.add_argument("--out", default="data/interim/incident_notices.jsonl")
    parser.add_argument(
        "--limit", type=int, default=None, help="max manifest lines to read"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    report = ingest_cache(args.raw_dir, args.out, limit=args.limit)
    print(f"\ningest: {report.parsed}/{report.total} notices parsed -> {args.out}")
    if report.skipped:
        print(f"skipped {report.skipped} malformed manifest line(s) (mid-scrape?)")
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
